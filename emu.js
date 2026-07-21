// emu.js — the SeedHammer tab: the real firmware GUI compiled to WebAssembly,
// running on a canvas. It boots lazily (the wasm is several MB, fetched only
// when the tab first opens), paints the device screen, forwards touch as the
// device's only navigation input, and taps in the plate you composed on the
// editor tabs as a synthetic NFC scan (via nfc-bus.js).
"use strict";
(function () {
  const WASM_URL = "emu.wasm";
  const EXEC_URL = "wasm_exec.js";

  let state = "idle"; // idle | booting | ready | error
  let canvas, ctx, statusEl;
  let firstFrame = false;
  let pending = null; // {kind:"curves"|"text", data} queued to tap once up
  let lastFed = null; // last data actually tapped, to skip redundant re-taps
  let installed = false; // canvas/listeners installed once, survives boot retries

  function setStatus(m) { if (statusEl) statusEl.textContent = m; }

  function installCanvas() {
    if (installed) return; // once only, or a boot retry double-binds the pointer listeners
    installed = true;
    canvas = document.getElementById("emuScreen");
    statusEl = document.getElementById("emuStatus");
    ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;

    // Go paints the firmware screen one dirty chunk per call.
    window.seedhammerBlit = (pixels, x, y, w, h) => {
      if (!firstFrame) { firstFrame = true; onFirstFrame(); }
      ctx.putImageData(new ImageData(pixels, w, h), x, y);
    };

    // Drag = the touch navigation the device uses; there is no other input.
    const at = (e) => {
      const r = canvas.getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(canvas.width - 1, Math.floor((e.clientX - r.left) * canvas.width / r.width))),
        y: Math.max(0, Math.min(canvas.height - 1, Math.floor((e.clientY - r.top) * canvas.height / r.height))),
      };
    };
    let down = false;
    canvas.addEventListener("pointerdown", (e) => {
      down = true;
      canvas.setPointerCapture && canvas.setPointerCapture(e.pointerId);
      const p = at(e);
      window.seedhammerTouch && window.seedhammerTouch(p.x, p.y, true);
    });
    window.addEventListener("pointerup", (e) => {
      if (!down) return;
      down = false;
      const p = at(e);
      window.seedhammerTouch && window.seedhammerTouch(p.x, p.y, false);
    });
    window.addEventListener("pointermove", (e) => {
      if (!down) return;
      const p = at(e);
      window.seedhammerTouch && window.seedhammerTouch(p.x, p.y, true);
    });
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error("failed to load " + src));
      document.head.appendChild(s);
    });
  }

  async function boot() {
    if (state === "booting" || state === "ready") return;
    state = "booting";
    installCanvas();
    setStatus("Loading the firmware…");
    try {
      await loadScript(EXEC_URL); // defines the Go class
      const go = new Go();
      let instance;
      try {
        const r = await WebAssembly.instantiateStreaming(fetch(WASM_URL), go.importObject);
        instance = r.instance;
      } catch (_) {
        // Fallback for hosts that don't serve application/wasm.
        const buf = await (await fetch(WASM_URL)).arrayBuffer();
        const r = await WebAssembly.instantiate(buf, go.importObject);
        instance = r.instance;
      }
      state = "ready";
      go.run(instance); // runs the UI loop; does not resolve until the app exits
    } catch (e) {
      state = "error";
      setStatus("Could not load the emulator: " + e.message);
    }
  }

  function onFirstFrame() {
    setStatus("Drag to navigate — it's a touch device. Use “Load composed plate” to tap in your design.");
    if (pending != null) { doFeed(pending); pending = null; }
  }

  // doFeed taps a {kind, data} into the device: a curves plate from the editor
  // or plain text (a seed/descriptor) forwarded from the Coldcard emulator.
  function doFeed(item) {
    if (!item || !item.data) return;
    const bus = window.NFCBus;
    if (!bus) return;
    const ok = item.kind === "text" ? bus.feedEmuText(item.data) : bus.feedEmu(item.data);
    if (ok) {
      lastFed = item.data;
      setStatus(item.kind === "text"
        ? "Tapped the wallet in from the Coldcard — watch the device read it."
        : "Tapped your plate in as an NFC scan — watch the device read it.");
    }
  }

  function queueOrFeed(item, always) {
    if (state === "error") state = "idle";
    if (state === "idle") { pending = item; boot(); return; }
    if (state === "booting") { pending = item; return; }
    if (always || item.data !== lastFed) doFeed(item);
  }

  // activate: called when the SeedHammer tab opens from an editor tab. Boots on
  // first open and taps in the current plate; on a later reopen it re-taps only
  // if the design changed, so returning to a device mid-flow doesn't disturb it.
  function activate(payload) { queueOrFeed({ kind: "curves", data: payload }, false); }

  // feed: the explicit "Load composed plate" button — always re-taps.
  function feed(payload) { queueOrFeed({ kind: "curves", data: payload }, true); }

  // feedText: a Coldcard export (seed or descriptor) tapped in as plain text.
  // Boots the device if the SeedHammer tab was never opened.
  function feedText(text) { queueOrFeed({ kind: "text", data: text }, true); }

  window.SeedHammerEmu = { activate, feed, feedText, boot };
})();
