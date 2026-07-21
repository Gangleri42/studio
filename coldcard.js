// coldcard.js — the Coldcard tab: the real Coldcard Mk5 MicroPython firmware
// compiled to WebAssembly, on an original device frame (no Coinkite photos).
// It boots lazily, paints the 128×64 OLED, forwards the keypad, and — the
// point of the hub — taps a "Share Seed / Descriptor via NFC" export into the
// SeedHammer emulator, simulating the real Coldcard-backup-to-plate flow.
//
// Adapted from the standalone cmd/coldcard-wasm/app.js harness. The wasm is a
// pure MicroPython+emsdk build with no firmware coupling; coldcard/ builds it,
// the deploy serves coldcard-mpy-coldcard-mk5.{mjs,wasm} from the site root.
"use strict";
(function () {
  const VARIANT = "coldcard-mk5";
  const WIDTH = 128, HEIGHT = 64;

  let state = "idle"; // idle | booting | ready | error
  let mp = null;
  let canvas, ctx, statusEl;
  let framed = false; // frame DOM/listeners installed once, survives boot retries

  function setStatus(m) { if (statusEl) statusEl.textContent = m; }

  // 128×64 mono, MONO_VLSB (8-pixel vertical pages, LSB on top).
  function paint(bytes) {
    if (!ctx) return;
    const img = ctx.createImageData(WIDTH, HEIGHT);
    for (let x = 0; x < WIDTH; x++) {
      for (let y = 0; y < HEIGHT; y++) {
        const page = (y >> 3) * WIDTH + x;
        const on = (bytes[page] >> (y & 7)) & 1;
        const off = (y * WIDTH + x) * 4;
        const v = on ? 0xff : 0x00;
        img.data[off] = v; img.data[off + 1] = v; img.data[off + 2] = v; img.data[off + 3] = 0xff;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  function loadScreen(msg) {
    if (!ctx) return;
    ctx.fillStyle = "#05070a"; ctx.fillRect(0, 0, WIDTH, HEIGHT);
    ctx.fillStyle = "#cbd2da"; ctx.font = "9px ui-monospace, monospace";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    msg.split("\n").forEach((line, i, a) => ctx.fillText(line, WIDTH / 2, HEIGHT / 2 + (i - (a.length - 1) / 2) * 11));
  }

  function injectKey(key) {
    if (!mp) return;
    try {
      mp.runPython(`import glob; glob.numpad.inject(${JSON.stringify(key)})`);
    } catch (e) { /* firmware not ready for input yet */ }
  }

  function installFrame() {
    if (framed) return; // once only, or a boot retry double-binds every keypad button
    framed = true;
    canvas = document.getElementById("ccScreen");
    statusEl = document.getElementById("ccStatus");
    ctx = canvas.getContext("2d", { alpha: false });
    ctx.imageSmoothingEnabled = false;
    // Keypad: the frame's .cckey buttons carry data-key.
    document.querySelectorAll("#ccKeypad .cckey").forEach((b) =>
      b.addEventListener("click", () => injectKey(b.dataset.key)));
  }

  async function boot() {
    if (state === "booting" || state === "ready") return;
    state = "booting";
    installFrame();
    loadScreen("Loading\nColdcard Mk5…");
    setStatus("Loading the Coldcard firmware…");
    let mod;
    try {
      mod = await import(`./coldcard-mpy-${VARIANT}.mjs`);
    } catch (e) {
      state = "error";
      loadScreen("firmware build\npending");
      setStatus("Coldcard wasm not present — the deploy builds it (see coldcard/README).");
      return;
    }
    try {
      mp = await mod.loadMicroPython({
        heapsize: 4 * 1024 * 1024,
        pystack: 32 * 1024,
        stdout: (s) => console.log(s),
        stderr: (s) => console.warn(s),
      });
      window.coldcardScreenPaint = paint;
      mp.runPython("import boot");
      mp.runPython("import main");
      state = "ready";
      setStatus("Coldcard Mk5 running. Navigate with the keypad, or send a wallet to the emulator below.");
      pollScreen();
      pollNdef();
    } catch (e) {
      state = "error";
      loadScreen("boot raised");
      setStatus("Coldcard boot error: " + (e.message || e));
    }
  }

  function pollScreen() {
    let last = -1;
    setInterval(() => {
      if (!mp) return;
      try {
        const st = mp._module.FS.stat("/work/screen.bin");
        if (st.mtime.getTime() === last) return;
        last = st.mtime.getTime();
        paint(mp._module.FS.readFile("/work/screen.bin"));
      } catch (_) {}
    }, 50);
  }

  // The export seam: the firmware writes an NDEF tag image to MEMFS when it
  // shares a seed/descriptor over NFC. We poll, decode the text record, and
  // tap it into the SeedHammer emulator — the Coldcard-to-plate flow.
  function pollNdef() {
    let lastTick = -1;
    setInterval(() => {
      if (!mp) return;
      try {
        const st = mp._module.FS.stat("/work/nfc-dump.ndef");
        // Key on mtime, not size: re-sharing the same seed (or a descriptor of
        // the same byte length) rewrites the file to an identical size, which a
        // size check would miss — the Share button would then do nothing.
        const tick = st.mtime.getTime();
        if (st.size > 0 && tick !== lastTick) {
          lastTick = tick;
          forwardExport(mp._module.FS.readFile("/work/nfc-dump.ndef"));
        }
      } catch (_) {}
    }, 100);
  }

  function forwardExport(bytes) {
    const text = decodeNdefText(bytes);
    if (!text) return;
    setStatus(`Sent the ${text.split(" ").length > 6 ? "seed" : "wallet"} to the SeedHammer emulator…`);
    if (window.SeedHammerEmu) window.SeedHammerEmu.feedText(text);
    // Show the SeedHammer device so the operator watches it read the tap.
    if (window.openSeedHammerFromColdcard) window.openSeedHammerFromColdcard();
  }

  // Walks a Type-2 NDEF tag image (CC bytes, TLV 0x03, record(s), 0xFE) and
  // returns the first Well-Known Text record's UTF-8 body.
  function decodeNdefText(bytes) {
    let i = 0;
    while (i < bytes.length && bytes[i] !== 0x03) i++;
    if (i >= bytes.length) return "";
    i++;
    let len = bytes[i++];
    if (len === 0xff) { len = (bytes[i] << 8) | bytes[i + 1]; i += 2; }
    const end = i + len;
    while (i < end) {
      const hdr = bytes[i++];
      const tnf = hdr & 0x07, sr = (hdr & 0x10) !== 0;
      const tl = bytes[i++];
      const pl = sr ? bytes[i++] : ((bytes[i] << 24) | (bytes[i + 1] << 16) | (bytes[i + 2] << 8) | bytes[i + 3]);
      if (!sr) i += 4;
      const idLen = (hdr & 0x08) ? bytes[i++] : 0;
      const type = String.fromCharCode(...bytes.slice(i, i + tl));
      i += tl + idLen;
      const payload = bytes.slice(i, i + pl);
      i += pl;
      if (tnf === 0x01 && type === "T") {
        const langLen = payload[0] & 0x3f;
        return new TextDecoder().decode(payload.slice(1 + langLen));
      }
    }
    return "";
  }

  function shareSeed() {
    if (state !== "ready") return;
    try { mp.runPython("import cc_share; cc_share.share_seed_via_nfc()"); }
    catch (e) { setStatus("Send to emulator failed: " + (e.message || e)); }
  }
  function shareDescriptor() {
    if (state !== "ready") return;
    try { mp.runPython("import cc_share; cc_share.share_descriptor_via_nfc()"); }
    catch (e) { setStatus("Send to emulator failed: " + (e.message || e)); }
  }

  window.ColdcardEmu = { boot, shareSeed, shareDescriptor };
})();
