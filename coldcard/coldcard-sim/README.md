# `cmd/coldcard-sim` — Coldcard simulator + WebSocket bridge

A non-official educational simulator. **Reference-only integration** — nothing
from upstream [`Coldcard/firmware`](https://github.com/Coldcard/firmware) is
committed in this repo. `setup.sh` clones it at a pinned commit at first
build, and `external/` is `.gitignore`'d. A `bridge.py` daemon watches the
simulator's NFC dump file and feeds the captured NDEF payloads into the
SeedHammer combined simulator ([`cmd/webnfc-sim`](../webnfc-sim/)) so the
canonical "tap a Coldcard against the SH2 device" flow works without
hardware.

Coldcard Mk4 / Q1 hardware has been the main historical input source for
SeedHammer. This integration re-platforms that flow onto a simulator for demo,
test, and education. Not affiliated with Coinkite Inc.

## Layout

```
cmd/coldcard-sim/
├── setup.sh                  ← fetches Coldcard/firmware @ pinned SHA (gitignored target)
├── build.sh                  ← apt-check + venv + build coldcard-mpy
├── bridge.py                 ← WebSocket daemon on ws://127.0.0.1:33766/
├── README.md                 ← this file
├── .gitignore                ← excludes external/, venv/
├── external/firmware/        ← fetched at build time — NOT committed
└── venv/                     ← Python virtualenv — NOT committed
```

Pinned upstream rev (override with `COLDCARD_REV=<sha>`):
- `ca06dfd2509eacfad333be9d35ed274559915d0e`  (2026-03-05, v5.5.0-26)

## One-time setup

Install apt prerequisites (Ubuntu 24.04 LTS reference):

```sh
sudo apt install -y libsdl2-dev libusb-1.0-0-dev libudev-dev \
                    autoconf libtool python3-venv python3-dev
```

Build the simulator + venv (one command — fetches firmware on first run):

```sh
bash cmd/coldcard-sim/build.sh
```

`setup.sh` is invoked automatically by `build.sh`. To fetch only (no build):

```sh
bash cmd/coldcard-sim/setup.sh
```

Build prints `[build] OK — …/coldcard-mpy` on success. Fresh-clone disk
footprint is ~250 MB (firmware + only the submodules the unix port actually
needs). Coldcard's full recursive submodule set would pull pico-sdk + tinyusb
+ nrfx (multi-GB STM32-only deps) which `setup.sh` deliberately skips.

## Running

Two processes — start the **bridge first** (so it can attach a sim work-dir
watcher when the sim comes up), then the headless **sim**:

```sh
# Terminal 1: bridge
cmd/coldcard-sim/venv/bin/python cmd/coldcard-sim/bridge.py

# Terminal 2: simulator (Mk4, headless, segregated work dir, no SE secrets)
cmd/coldcard-sim/external/firmware/unix/simulator.py --mk4 --headless --eff -w
```

Then open the SeedHammer combined simulator:

```sh
bash cmd/webnfc-sim/build.sh
python3 -m http.server 8781 -d cmd/webnfc-sim
# open http://127.0.0.1:8781/ in a browser
```

Click the **Coldcard Mk4 (sim)** tab. Status indicator turns green when the
bridge sees the sim. Click **Share Seed Words → SeedHammer** — within ~2 s the
right-hand firmware emulator advances through scan → seed confirmation →
EngraveScreen.

The **Custom Text (debug)** path bypasses the bridge entirely; useful for
exercising the SeedHammer parser without needing the Coldcard sim at all.

## Bridge wire protocol

See `bridge.py`'s top-of-file docstring. Summary:

| Direction | Frame |
|---|---|
| → bridge | `{"op":"ping"}` |
| → bridge | `{"op":"set-seed", "words":"…"}` |
| → bridge | `{"op":"share-seed"}` |
| → bridge | `{"op":"reset"}` |
| bridge → | `{"status":"ok", "sim":"connected"|"disconnected"}` |
| bridge → | `{"status":"setting-seed"|"seed-set"|"sharing"|"shared"|"reset"|"error", "message":"…"}` |
| bridge → | `{"event":"export", "kind":"seed-words"|"descriptor"|"text"|"unknown", "text":"…", "bytes": N}` |

Origin allowlist defaults: `http://127.0.0.1:8781`, `http://localhost:8781`,
`http://127.0.0.1:8001`, `http://localhost:8001`, `https://seedhammer.com`,
`null` (file://), and `""` (no Origin header). Binding is `127.0.0.1:33766`
only — no remote access.

## What plugs into what

```
┌── Coldcard sim (headless) ─────────┐
│  unix/simulator.py --mk4 --headless│
│  shared/nfc.py: share_text(words)  │
│    → ndefMaker.bytes()             │
│    → big_write(buf)                │
│       writes complete tag image:   │
│       CC + TLV + record + 0xFE     │
│       → unix/work/nfc-dump.ndef    │
└────────────┬───────────────────────┘
             │ inotify-style poll, 100 ms
             ▼
┌── cmd/coldcard-sim/bridge.py ──────┐
│  parse_tag_image() → classify      │
│  WebSocket broadcast: {event:…}    │
└────────────┬───────────────────────┘
             │ ws://127.0.0.1:33766/
             ▼
┌── cmd/webnfc-sim/coldcard.js ──────┐
│  on event:"export" of kind         │
│  seed-words → seedhammerSynthTapText(text)
│    → emu.wasm: nfcReader.tap(bytes)│
│    → nfc/ndef parse                │
│    → gui/scan: bip39.Parse         │
│    → backup.EngraveSeed            │
│    → EngraveScreen                 │
└────────────────────────────────────┘
```

## License

This directory's own files (`setup.sh`, `build.sh`, `bridge.py`, `README.md`)
are under the [Unlicense](../../LICENSE), same as the rest of SeedHammer.

`external/firmware/` is fetched by `setup.sh` from upstream
`Coldcard/firmware`, which ships under **MIT + Commons Clause v1.0**
(Coinkite Inc.). Nothing from upstream is committed in this repo — neither
a submodule pointer nor a `.gitmodules` entry. The only Coldcard reference
in our tree is the pinned commit SHA inside `setup.sh`.

The Commons Clause carves "Sell" out of the otherwise-MIT grant — SeedHammer
is Unlicense and not sold, so the carve-out is not implicated in this
integration.
