// cmd/coldcard-wasm/app.js — variant selector + WASM driver + JS↔Python bridge.
//
// Loads coldcard-mpy-<variant>.mjs (built by cmd/coldcard-wasm/build.sh)
// for the active variant, wires:
//   - JS  → Python keycodes via mp.pyimport('numpad').inject(key)
//   - Py  → JS framebuffer via window.coldcardScreenPaint(bytes)
//   - Py  → JS NDEF export via MEMFS /work/nfc-dump.ndef (read on FS write)
//
// Per AD-9, this is the standalone page; cmd/webnfc-sim/coldcard.js wires
// the same hooks into the integrated combined-sim shell.

const VARIANTS = {
  "coldcard-mk5": { width: 128, height: 64, colour: false },
  "coldcard-q1":  { width: 320, height: 240, colour: true  },
};

const STORE_KEY = "coldcard-wasm-variant";
let active = null;
let mp = null;
let mpVariant = null;

const tabs = document.querySelectorAll(".variant-switch button");
const frames = document.querySelectorAll(".device-frame");
const statusEl = document.getElementById("status-line");
const mirrorEl = document.getElementById("screen-mirror-body");

function pickVariant() {
  const fromHash = location.hash.replace("#", "");
  if (VARIANTS[fromHash]) return fromHash;
  const stored = localStorage.getItem(STORE_KEY);
  if (VARIANTS[stored]) return stored;
  return "coldcard-mk5";
}

function setStatus(msg) {
  statusEl.textContent = msg;
}

// paintFrame + placeholderPaint are intentionally duplicated in
// cmd/webnfc-sim/coldcard-wasm.js (combined-sim tab). Keep both copies
// in sync — pixel-format or placeholder-text changes land in both.
function paintFrame(canvas, bytes, variant) {
  const ctx = canvas.getContext("2d", { alpha: false });
  const w = canvas.width;
  const h = canvas.height;
  const img = ctx.createImageData(w, h);
  if (!variant.colour) {
    // 128×64 mono, MONO_VLSB (page rows of 8 vertical pixels, LSB top).
    for (let x = 0; x < w; x++) {
      for (let y = 0; y < h; y++) {
        const page = (y >> 3) * w + x;
        const bit = (bytes[page] >> (y & 7)) & 1;
        const off = (y * w + x) * 4;
        const v = bit ? 0xff : 0x00;
        img.data[off + 0] = v;
        img.data[off + 1] = v;
        img.data[off + 2] = v;
        img.data[off + 3] = 0xff;
      }
    }
  } else {
    // 320×240 RGB565 (Q1 — graphics_q1.py packs two bytes per pixel,
    // little-endian RRRRRGGGGGG BBBBB).
    for (let i = 0; i < w * h; i++) {
      const lo = bytes[i * 2];
      const hi = bytes[i * 2 + 1];
      const v = (hi << 8) | lo;
      const r = ((v >> 11) & 0x1f) << 3;
      const g = ((v >>  5) & 0x3f) << 2;
      const b = ( v        & 0x1f) << 3;
      const off = i * 4;
      img.data[off + 0] = r;
      img.data[off + 1] = g;
      img.data[off + 2] = b;
      img.data[off + 3] = 0xff;
    }
  }
  ctx.putImageData(img, 0, 0);
}

function placeholderPaint(canvas, variant, msg) {
  const ctx = canvas.getContext("2d", { alpha: false });
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = variant.colour ? "#fa3" : "#fff";
  ctx.font = variant.colour ? "16px ui-monospace, monospace" : "10px ui-monospace, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const lines = msg.split("\n");
  const lh = variant.colour ? 20 : 12;
  const y0 = canvas.height / 2 - (lines.length - 1) * lh / 2;
  for (let i = 0; i < lines.length; i++) {
    ctx.fillText(lines[i], canvas.width / 2, y0 + i * lh);
  }
}

function setMirror(text) {
  if (!text) return;
  mirrorEl.textContent = text;
}

window.coldcardScreenPaint = (bytes) => {
  const frame = document.querySelector(`.device-frame[data-variant="${mpVariant}"]`);
  if (!frame) return;
  const canvas = frame.querySelector(".device-frame__screen");
  paintFrame(canvas, bytes, VARIANTS[mpVariant]);
};

window.coldcardMirror = (text) => setMirror(text);

async function loadVariant(name) {
  const variant = VARIANTS[name];
  if (!variant) throw new Error(`unknown variant ${name}`);
  active = name;
  mpVariant = null;
  for (const f of frames) f.hidden = (f.dataset.variant !== name);
  for (const t of tabs) t.setAttribute("aria-selected", t.dataset.source === name || t.dataset.variant === name ? "true" : "false");
  localStorage.setItem(STORE_KEY, name);
  history.replaceState(null, "", `#${name}`);

  const frame = document.querySelector(`.device-frame[data-variant="${name}"]`);
  const canvas = frame.querySelector(".device-frame__screen");
  placeholderPaint(canvas, variant, "Loading\ncoldcard-mpy-" + name + ".mjs");

  let mod;
  try {
    mod = await import(`./coldcard-mpy-${name}.mjs`);
  } catch (err) {
    setStatus(`MicroPython build not present — run cmd/coldcard-wasm/setup.sh && bash cmd/coldcard-wasm/build.sh`);
    placeholderPaint(canvas, variant, "WASM build pending\nrun cmd/coldcard-wasm/build.sh");
    return;
  }

  setStatus(`Booting ${name}…`);
  mp = await mod.loadMicroPython({
    heapsize: 4 * 1024 * 1024,
    // Default pystack of 2 KiB exhausts during shared/lcd_display.py's
    // show() loop on Q1 — splash → image → show_zpixels → struct.unpack
    // chains push the value stack deep. 32 KiB has plenty of headroom.
    pystack: 32 * 1024,
    stdout: (s) => console.log(s),
    stderr: (s) => console.warn(s),
  });
  mpVariant = name;
  // Expose the live MicroPython instance to other JS — Puppeteer tests
  // + cmd/webnfc-sim/coldcard-wasm.js need to invoke cc_share helpers
  // without re-loading the .mjs.
  window.coldcardMp = mp;
  window.coldcardShareSeed = () => mp.runPython("import cc_share; cc_share.share_seed_via_nfc()");
  window.coldcardShareDescriptor = () => mp.runPython("import cc_share; cc_share.share_descriptor_via_nfc()");

  // Plan A: boot the real Coldcard firmware menu. The webassembly port's
  // asyncio schedules tasks via js.setTimeout — Python returns from
  // `import main` after run_forever() exits (boot.py shim), and JS
  // keeps firing the queued tasks long after. main.py raises
  // RuntimeError('main.stop') on exit; we swallow it via boot.py's
  // die_with_debug shim so the firmware doesn't paint Yikes.
  try {
    mp.runPython("import boot");
    setStatus(`${name} booting Coldcard firmware…`);
    mp.runPython("import main");
    setStatus(`${name} firmware running.`);
  } catch (err) {
    console.error(err);
    setStatus(`${name} boot raised: ${err.message || err}`);
    placeholderPaint(canvas, variant, "Firmware boot raised\n" + (err.message || String(err)));
    return;
  }

  pollScreen();
  pollNdef();
}

function pollScreen() {
  if (!mp) return;
  let lastTick = -1;
  setInterval(() => {
    if (!mp || !mpVariant) return;
    try {
      const stat = mp._module.FS.stat("/work/screen.bin");
      if (stat.mtime.getTime() === lastTick) return;
      lastTick = stat.mtime.getTime();
      const bytes = mp._module.FS.readFile("/work/screen.bin");
      window.coldcardScreenPaint(bytes);
    } catch (_) {}
  }, 50);
}

function pollNdef() {
  // The Emscripten FS API doesn't reliably surface write events on Node-style
  // trackingDelegate in browsers, so we poll the dump file at 100 ms.
  let lastSize = 0;
  setInterval(() => {
    if (!mp) return;
    try {
      const stat = mp._module.FS.stat("/work/nfc-dump.ndef");
      if (stat.size > 0 && stat.size !== lastSize) {
        lastSize = stat.size;
        const bytes = mp._module.FS.readFile("/work/nfc-dump.ndef");
        forwardExport(bytes);
      }
    } catch (_) { /* file not yet written */ }
  }, 100);
}

function forwardExport(bytes) {
  const text = decodeNdefText(bytes);
  if (typeof window.seedhammerSynthTapText === "function" && text) {
    window.seedhammerSynthTapText(text);
    setStatus(`Sent ${text.length}-char payload to SeedHammer (parent page).`);
  } else if (text) {
    setStatus(`Captured NFC payload: ${text.slice(0, 32)}${text.length > 32 ? "…" : ""}`);
    setMirror(text);
  }
}

function decodeNdefText(bytes) {
  // Walks a Type-2 NDEF tag image: CC bytes, TLV(0x03 len), record(s), 0xFE.
  // Extracts the first 'T' (TNF=0x01, Well-Known Text) record's UTF-8 body.
  let i = 0;
  while (i < bytes.length && bytes[i] !== 0x03) i++;
  if (i >= bytes.length) return "";
  i++; // past 0x03
  let len = bytes[i++];
  if (len === 0xff) {
    len = (bytes[i] << 8) | bytes[i + 1];
    i += 2;
  }
  const end = i + len;
  while (i < end) {
    const hdr = bytes[i++];
    const tnf = hdr & 0x07;
    const sr  = (hdr & 0x10) !== 0;
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

// ---- key handlers ----

document.addEventListener("click", (ev) => {
  const k = ev.target.closest(".key");
  if (!k) return;
  injectKey(k.dataset.key);
});

document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "INPUT" || ev.target.tagName === "TEXTAREA") return;
  let k = ev.key;
  if (/^[0-9a-z]$/.test(k)) {/* literal */}
  else if (k === "Enter") k = "y";
  else if (k === "Escape") k = "x";
  else if (k === "ArrowLeft") k = "l";
  else if (k === "ArrowRight") k = "r";
  else if (k === " ") k = " ";
  else if (k === "Backspace") k = "backspace";
  else return;
  injectKey(k);
  ev.preventDefault();
});

function injectKey(key) {
  if (!mp) return;
  // shared/numpad.py NumpadBase.inject pushes (key, '') into the
  // async event queue that shared/ux.py awaits. That's the canonical
  // path for both touch and membrane keypads — and the same path
  // the on-device hardware ISR uses.
  try {
    mp.runPython(`import glob; glob.numpad.inject(${JSON.stringify(key)})`);
  } catch (err) {
    console.warn("inject failed", err);
  }
}

for (const t of tabs) {
  t.addEventListener("click", () => loadVariant(t.dataset.variant));
}

document.getElementById("btn-share-seed")?.addEventListener("click", () => {
  if (window.coldcardShareSeed) window.coldcardShareSeed();
});
document.getElementById("btn-share-descriptor")?.addEventListener("click", () => {
  if (window.coldcardShareDescriptor) window.coldcardShareDescriptor();
});

window.addEventListener("hashchange", () => {
  const next = pickVariant();
  if (next !== active) loadVariant(next);
});

loadVariant(pickVariant());
