#!/usr/bin/env python3
# Coldcard sim ↔ SeedHammer webnfc-sim bridge daemon.
#
# Watches the simulator's NFC dump file (unix/work/nfc-dump.ndef) and emits
# parsed payloads over a localhost WebSocket so the SeedHammer combined sim's
# Coldcard tab can forward them into emu.wasm via window.seedhammerSynthTapText.
#
# Mirrors the cmd/webnfc/bridge/sh2-bridge.py shape:
#   - 127.0.0.1 bind only (no remote access)
#   - origin allowlist
#   - JSON wire frames
#
# Wire protocol (the JS side lives in cmd/webnfc-sim/coldcard.js):
#   page → daemon:
#     {"op":"ping"}                         liveness probe
#     {"op":"set-seed", "words":"…"}        load BIP-39 mnemonic (Phase 3 — spawns a fresh --headless sim with --seed)
#     {"op":"share-seed"}                   drive sim through Settings → NFC → Share Seed Words via --seq
#     {"op":"share-descriptor"}             (v2; multisig wallet must be pre-loaded)
#     {"op":"reset"}                        wipe sim state, restart
#   daemon → page:
#     {"status":"ok",         "sim":"connected"|"disconnected"}
#     {"status":"setting-seed"|"seed-set"|"sharing"|"shared"|"reset"|"error", "message":"…"}
#     {"event":"export",
#      "kind":"seed-words"|"descriptor"|"text"|"unknown",
#      "text":"…",             # for seed-words/descriptor/text
#      "raw_b64":"…",          # for unknown (full NDEF record payload)
#      "bytes": N}
#
# The classifier on the export side is heuristic:
#   - TNF=0x01 'T' Well-Known Text → strip status+lang prefix, UTF-8 decode the payload.
#     Classify the text:
#       * 12 or 24 lowercase whitespace-separated words → "seed-words"
#       * starts with one of: wsh(, sh(, wpkh(, pkh(, tr(, sortedmulti( → "descriptor"
#       * otherwise → "text"
#   - TNF=0x02 MIME / TNF=0x04 External / etc → "unknown", payload base64'd.
#
# Run:
#   pip install websockets watchdog
#   python3 cmd/coldcard-sim/bridge.py [--work-dir /tmp/cc-simulators/<pid>]
#
# License: Unlicense (same as the parent repo).

from __future__ import annotations

import argparse
import asyncio
import base64
import glob
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import websockets
except ImportError:
    sys.stderr.write("error: 'websockets' not installed. Run: pip install websockets watchdog\n")
    sys.exit(2)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAVE_WATCHDOG = True
except ImportError:
    HAVE_WATCHDOG = False

# ---------------------------------------------------------------------------
# Constants.
# ---------------------------------------------------------------------------

BIND_HOST = "127.0.0.1"
BIND_PORT = 33766
ALLOWED_ORIGINS = {
    "http://127.0.0.1:8781",
    "http://localhost:8781",
    "http://127.0.0.1:8001",
    "http://localhost:8001",
    "https://seedhammer.com",
    "null",  # file:// loads
    "",      # some clients omit Origin
}

NFC_FILE = "nfc-dump.ndef"          # the sim writes here
CC_FILE_LEN = 8                     # Type-5 Capability Container fixed length (E2 43 00 01 00 00 04 00)
MAX_NFC_SIZE = 8196                 # MAX_NFC_SIZE + 196 overhead
DEBOUNCE_SECONDS = 0.5              # collapse rapid identical writes
MIN_GAP_BETWEEN_EVENTS = 3.0        # rate-limit events regardless of content
                                    # (defence against rotating-share loops)
SIM_HEALTHCHECK_INTERVAL = 5.0      # poll for the simulator process

# BIP-39 English wordlist sniff — match a few well-known short words.
BIP39_HINT = re.compile(r"^[a-z]+(?:\s+[a-z]+){11,23}$")
DESCRIPTOR_PREFIX = re.compile(r"^(?:wsh|sh|wpkh|pkh|tr|sortedmulti|multi)\(")

# ---------------------------------------------------------------------------
# Locating the simulator work dir.
# ---------------------------------------------------------------------------


def find_sim_work_dir(explicit: Optional[str] = None) -> Optional[Path]:
    """Return the most-recently-modified /tmp/cc-simulators/* dir, or None."""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if p.is_dir() else None
    candidates = sorted(glob.glob("/tmp/cc-simulators/*"), key=os.path.getmtime, reverse=True)
    for c in candidates:
        if os.path.isdir(c) and (Path(c) / NFC_FILE).exists():
            return Path(c)
    # Fallback: the in-tree unix/work/ dir (non-segregated sims).
    repo_root = Path(__file__).resolve().parent
    for guess in [
        repo_root / "external" / "firmware" / "unix" / "work",
        Path.cwd() / "unix" / "work",
    ]:
        if (guess / NFC_FILE).exists():
            return guess
    return None


def sim_is_running() -> bool:
    """Cheap probe: does any cc-simulators/<pid> have a live socket?"""
    socks = glob.glob("/tmp/ckcc-simulator*.sock")
    for s in socks:
        # The socket file exists even if the sim exited. We rely on the
        # work-dir mtime + the segregated socket-by-pid convention.
        try:
            os.stat(s)
            return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------------------
# NDEF parsing — minimal, just enough for the records Coldcard emits.
# ---------------------------------------------------------------------------


class NdefRecord:
    __slots__ = ("mb", "me", "cf", "sr", "il", "tnf", "type_field", "id_field", "payload")

    def __init__(self) -> None:
        self.mb = self.me = self.cf = self.sr = self.il = False
        self.tnf = 0
        self.type_field = b""
        self.id_field = b""
        self.payload = b""


def parse_tag_image(buf: bytes) -> list[NdefRecord]:
    """Strip the Type-5 CC file + TLV framing and return raw NDEF records.

    Coldcard's ndefMaker.bytes() output:
      CC file (9 bytes, E2 43 00 01 00 00 04 00 03) | NDEF Message TLV (0x03) | records | Terminator (0xFE).
    """
    if len(buf) < CC_FILE_LEN + 2:
        return []
    # Skip CC file.
    pos = CC_FILE_LEN
    # Walk TLVs until we find the NDEF message TLV (0x03).
    while pos < len(buf):
        t = buf[pos]
        pos += 1
        if t == 0x00:
            continue  # null TLV — skip
        if t == 0xFE:
            return []  # terminator before NDEF message
        if t == 0x03:
            # Length: 1 byte unless 0xFF, then 2-byte BE.
            if pos >= len(buf):
                return []
            length = buf[pos]
            pos += 1
            if length == 0xFF:
                if pos + 2 > len(buf):
                    return []
                length = (buf[pos] << 8) | buf[pos + 1]
                pos += 2
            return _parse_records(buf[pos : pos + length])
        # Unknown TLV — read its length and skip.
        if pos >= len(buf):
            return []
        length = buf[pos]
        pos += 1
        if length == 0xFF:
            if pos + 2 > len(buf):
                return []
            length = (buf[pos] << 8) | buf[pos + 1]
            pos += 2
        pos += length
    return []


def _parse_records(buf: bytes) -> list[NdefRecord]:
    records: list[NdefRecord] = []
    pos = 0
    while pos < len(buf):
        if pos >= len(buf):
            break
        flags = buf[pos]
        pos += 1
        r = NdefRecord()
        r.mb = bool(flags & 0x80)
        r.me = bool(flags & 0x40)
        r.cf = bool(flags & 0x20)
        r.sr = bool(flags & 0x10)
        r.il = bool(flags & 0x08)
        r.tnf = flags & 0x07
        if pos >= len(buf):
            break
        type_len = buf[pos]
        pos += 1
        if r.sr:
            if pos >= len(buf):
                break
            payload_len = buf[pos]
            pos += 1
        else:
            if pos + 4 > len(buf):
                break
            payload_len = int.from_bytes(buf[pos : pos + 4], "big")
            pos += 4
        id_len = 0
        if r.il:
            if pos >= len(buf):
                break
            id_len = buf[pos]
            pos += 1
        if pos + type_len + id_len + payload_len > len(buf):
            break
        r.type_field = buf[pos : pos + type_len]
        pos += type_len
        r.id_field = buf[pos : pos + id_len]
        pos += id_len
        r.payload = buf[pos : pos + payload_len]
        pos += payload_len
        records.append(r)
        if r.me:
            break
    return records


def classify_record(rec: NdefRecord) -> dict:
    """Turn one NDEF record into a {kind, text|raw_b64, bytes} dict."""
    out: dict = {"bytes": len(rec.payload)}
    if rec.tnf == 0x01 and rec.type_field == b"T":
        # Well-Known Text — strip status byte + lang code.
        if rec.payload:
            status = rec.payload[0]
            lang_len = status & 0x3F
            text = rec.payload[1 + lang_len :].decode("utf-8", "replace")
            out["text"] = text
            text_lc = text.strip().lower()
            if BIP39_HINT.match(text_lc):
                out["kind"] = "seed-words"
            elif DESCRIPTOR_PREFIX.match(text_lc):
                out["kind"] = "descriptor"
            else:
                out["kind"] = "text"
            return out
        out["kind"] = "text"
        out["text"] = ""
        return out
    if rec.tnf == 0x01 and rec.type_field == b"U":
        out["kind"] = "text"
        out["text"] = "(URI record — not engravable)"
        out["raw_b64"] = base64.b64encode(rec.payload).decode("ascii")
        return out
    # MIME / External / Unknown — for now, debug-only base64.
    out["kind"] = "unknown"
    out["raw_b64"] = base64.b64encode(rec.payload).decode("ascii")
    return out


# ---------------------------------------------------------------------------
# WebSocket hub — broadcasts events to all connected pages.
# ---------------------------------------------------------------------------


class Hub:
    def __init__(self) -> None:
        self.clients: set[websockets.WebSocketServerProtocol] = set()

    async def register(self, ws) -> None:
        self.clients.add(ws)

    async def unregister(self, ws) -> None:
        self.clients.discard(ws)

    async def broadcast(self, frame: dict) -> None:
        if not self.clients:
            return
        msg = json.dumps(frame)
        await asyncio.gather(*[c.send(msg) for c in list(self.clients)], return_exceptions=True)


# ---------------------------------------------------------------------------
# File watcher — fires when nfc-dump.ndef changes.
# ---------------------------------------------------------------------------


class NfcFileWatcher:
    """Owns the watched file path + a last-seen hash. The actual broadcast
    happens in poll_loop so we stay on the bridge's running event loop."""

    def __init__(self, work_dir: Path) -> None:
        self.path = work_dir / NFC_FILE
        self._last_hash: Optional[bytes] = None
        self._last_event_at = 0.0

    def changed_bytes(self) -> Optional[bytes]:
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return None
        import hashlib

        h = hashlib.sha256(data).digest()
        now = time.time()
        if h == self._last_hash:
            return None
        # Rate-limit: at least MIN_GAP_BETWEEN_EVENTS between any two emits,
        # regardless of payload content. Stops rotating-share loops (multiple
        # async share_text() tasks alternating in the sim's event loop) from
        # flooding the page.
        if now - self._last_event_at < MIN_GAP_BETWEEN_EVENTS:
            return None
        self._last_hash = h
        self._last_event_at = now
        return data


# ---------------------------------------------------------------------------
# Simulator process manager (Phase 3 — used for set-seed / share-seed).
# ---------------------------------------------------------------------------


class SimManager:
    """Owns the headless sim child process.

    Lifecycle:
      - .set_seed(words): kill any existing process, spawn a new one with --seed + --eff + --headless + --segregate.
      - .share_seed():  send the keystroke sequence that drives Settings → Advanced/Tools → NFC Tools → Share Seed Words (or whichever variant the firmware ships).
      - .reset():       kill the process.
    """

    def __init__(self, simulator_py: Path) -> None:
        self.simulator_py = simulator_py
        self.proc: Optional[subprocess.Popen] = None
        self.work_dir: Optional[Path] = None
        self.cwd = simulator_py.parent

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def kill(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            except OSError:
                pass
        self.proc = None
        self.work_dir = None

    def set_seed(self, words: str) -> Path:
        self.kill()
        words = " ".join(words.strip().split())
        argv = [
            sys.executable,
            str(self.simulator_py),
            "--mk4",
            "--headless",
            "--segregate",
            "--eff",
            "--seed",
            words,
        ]
        env = os.environ.copy()
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        self.proc = subprocess.Popen(
            argv,
            cwd=str(self.cwd),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Locate the new sim's work dir (waits up to 5s for it to appear).
        deadline = time.time() + 5.0
        while time.time() < deadline:
            cand = Path(f"/tmp/cc-simulators/{self.proc.pid}")
            if cand.is_dir():
                self.work_dir = cand
                return cand
            time.sleep(0.1)
        raise RuntimeError(f"sim PID {self.proc.pid} did not create a segregated work dir")

    def share_seed_via_keys(self) -> None:
        """Drive the menu via --seq is set-once-at-start; for an already-running
        sim we'd need ckcc-protocol. For v1 we accept that set-seed restarts the
        sim with the share-seed sequence baked into --seq.
        """
        raise NotImplementedError(
            "share_seed_via_keys is unused — see set_seed_and_share below"
        )

    def set_seed_and_share(self, words: str) -> Path:
        """Start the sim with the seed AND the keystroke sequence that drives
        Settings → Advanced → NFC Tools → Share Seed Words in one shot.

        The exact keystroke sequence depends on Coldcard's menu structure for
        the Mk4. Best-effort: `Mk4 menu navigation is character-by-character
        via 'y' (yes/enter) and digit keys for menu indices'.
        """
        self.kill()
        words = " ".join(words.strip().split())
        # --seq sends keystrokes after boot. y = Enter, then sequence to navigate
        # to Advanced/Tools → NFC Tools → Share Seed Words. The actual sequence
        # depends on menu layout — leave configurable.
        seq = os.environ.get("CC_SHARE_SEED_SEQ", "yyyy")  # placeholder
        argv = [
            sys.executable,
            str(self.simulator_py),
            "--mk4",
            "--headless",
            "--segregate",
            "--eff",
            "--seed",
            words,
            "--seq",
            seq,
        ]
        env = os.environ.copy()
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        self.proc = subprocess.Popen(
            argv,
            cwd=str(self.cwd),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.time() + 5.0
        while time.time() < deadline:
            cand = Path(f"/tmp/cc-simulators/{self.proc.pid}")
            if cand.is_dir():
                self.work_dir = cand
                return cand
            time.sleep(0.1)
        raise RuntimeError(f"sim PID {self.proc.pid} did not create a segregated work dir")


# ---------------------------------------------------------------------------
# Main daemon.
# ---------------------------------------------------------------------------


def find_ckcc_binary() -> Optional[str]:
    here = Path(__file__).resolve().parent
    cand = here / "venv" / "bin" / "ckcc"
    if cand.is_file():
        return str(cand)
    import shutil
    return shutil.which("ckcc")


async def drive_sim_share_text(words: str) -> None:
    """Drive a one-shot NFC NDEF write on the already-running Coldcard sim.

    Bypasses Coldcard's share_text() — that method spawns a long-running
    share_loop which keeps the NFC chip "presenting" the data for many
    seconds so a phone has time to tap. Calling it more than once stacks
    presenters that rotate writes to nfc-dump.ndef ad infinitum.

    Instead we call the underlying one-shot writer NFC.big_write(ndef_bytes)
    directly, after building the NDEF body with ndef.ndefMaker. ONE file
    write → ONE bridge poll → ONE export event → ONE page forward. Clean.
    """
    ckcc = find_ckcc_binary()
    if not ckcc:
        raise RuntimeError("ckcc CLI not found (run bash cmd/coldcard-sim/build.sh)")
    if not words:
        raise RuntimeError("share-seed: empty words (sim's loaded seed read-back not implemented)")

    # Build a real multi-line script. ckcc joins argv with spaces and the
    # firmware's exec() handles newlines fine (verified). Each line must be
    # self-contained — no implicit continuations.
    # big_write is async. Schedule it on the sim's running event loop with
    # uasyncio.create_task — fires once, writes once, no share_loop sticky
    # presenter.
    script = (
        "import nfc, ndef, uasyncio\n"
        "from glob import NFC\n"
        "nfc.NFCHandler.startup()\n"
        "n = ndef.ndefMaker()\n"
        "n.add_text(" + repr(words) + ")\n"
        "uasyncio.create_task(NFC.big_write(n.bytes()))\n"
    )
    proc = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: subprocess.run([ckcc, "--simulator", "exec", script],
                               capture_output=True, timeout=5),
    )
    out = (proc.stdout or b"") + (proc.stderr or b"")
    if b"Traceback" in out or proc.returncode != 0:
        raise RuntimeError(f"ckcc exec failed: {out.decode('utf-8','replace')[:300]}")


async def serve(hub: Hub, watcher_ref, sim: Optional[SimManager]):
    async def handle_client(ws):
        await hub.register(ws)
        # Initial state.
        await ws.send(json.dumps({"status": "ok", "sim": "connected" if ((sim and sim.is_alive()) or sim_is_running()) else "disconnected"}))
        try:
            async for raw in ws:
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                op = frame.get("op")
                if op == "ping":
                    await ws.send(json.dumps({"status": "ok", "sim": "connected" if ((sim and sim.is_alive()) or sim_is_running()) else "disconnected"}))
                elif op == "set-seed" or op == "share-seed":
                    if not sim_is_running():
                        await ws.send(json.dumps({"status": "error", "message": "Coldcard sim not running. Start it: cmd/coldcard-sim/external/firmware/unix/simulator.py --mk4 --headless --eff --seed \"<your words>\""}))
                        continue
                    words = (frame.get("words") or "").strip()
                    # Share-seed without explicit words: try to read the sim's loaded seed.
                    await hub.broadcast({"status": "setting-seed" if words else "sharing"})
                    try:
                        await drive_sim_share_text(words)
                        await hub.broadcast({"status": "sharing"})
                    except Exception as e:
                        logging.exception("share failed")
                        await hub.broadcast({"status": "error", "message": f"share: {e}"})
                elif op == "reset" and sim:
                    sim.kill()
                    await hub.broadcast({"status": "reset"})
                else:
                    await ws.send(json.dumps({"status": "error", "message": f"unknown op {op!r}"}))
        finally:
            await hub.unregister(ws)

    server = await websockets.serve(
        handle_client,
        BIND_HOST,
        BIND_PORT,
        max_size=2**20,
        origins=list(ALLOWED_ORIGINS),
    )
    logging.info("bridge listening on ws://%s:%d/", BIND_HOST, BIND_PORT)
    return server


async def poll_loop(hub: Hub, watcher_ref):
    """Tight poll on the NFC file mtime. Runs on the bridge's event loop so we
    can await hub.broadcast() directly. watcher_ref is a one-element list so
    main() can hot-swap the watcher when set-seed restarts the sim."""
    while True:
        w = watcher_ref[0]
        if w is not None and w.path.exists():
            data = w.changed_bytes()
            if data is not None:
                records = parse_tag_image(data)
                if records:
                    rec = records[0]
                    frame = classify_record(rec)
                    frame["event"] = "export"
                    logging.info("export: kind=%s bytes=%d", frame.get("kind"), frame["bytes"])
                    await hub.broadcast(frame)
                else:
                    logging.debug("no records in %d bytes", len(data))
        await asyncio.sleep(0.1)


def main():
    ap = argparse.ArgumentParser(description="Coldcard sim NFC bridge for SeedHammer webnfc-sim.")
    ap.add_argument("--work-dir", help="Sim work dir (default: auto-detect)")
    ap.add_argument("--simulator-py", help="Path to simulator.py for set-seed (default: ../external/firmware/unix/simulator.py)")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    here = Path(__file__).resolve().parent
    sim_py = Path(args.simulator_py) if args.simulator_py else here / "external" / "firmware" / "unix" / "simulator.py"
    sim_mgr: Optional[SimManager] = None
    if sim_py.is_file():
        sim_mgr = SimManager(sim_py)
        logging.info("sim launcher available: %s", sim_py)
    else:
        logging.warning("simulator.py not found at %s — set-seed will fail; build the sim first", sim_py)

    work_dir = find_sim_work_dir(args.work_dir)
    hub = Hub()
    watcher_ref: list[Optional[NfcFileWatcher]] = [None]
    if work_dir:
        logging.info("watching sim work dir: %s", work_dir)
        watcher_ref[0] = NfcFileWatcher(work_dir)
    else:
        logging.warning("no sim work dir found — start the sim or pass --work-dir")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    server = loop.run_until_complete(serve(hub, watcher_ref, sim_mgr))

    # Periodically rediscover the sim work dir (handles late sim startup).
    async def rediscover():
        while True:
            if watcher_ref[0] is None or not watcher_ref[0].path.exists():
                wd = find_sim_work_dir(args.work_dir)
                if wd:
                    if watcher_ref[0] is None:
                        watcher_ref[0] = NfcFileWatcher(wd)
                        logging.info("watcher attached: %s", watcher_ref[0].path)
                    elif watcher_ref[0].path.parent != wd:
                        watcher_ref[0] = NfcFileWatcher(wd)
                        logging.info("watcher re-attached: %s", watcher_ref[0].path)
            await asyncio.sleep(2.0)

    loop.create_task(rediscover())
    loop.create_task(poll_loop(hub, watcher_ref))

    def shutdown(_signum, _frame):
        if sim_mgr:
            sim_mgr.kill()
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_forever()
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()
        if sim_mgr:
            sim_mgr.kill()


if __name__ == "__main__":
    main()
