# `cmd/coldcard-wasm` — in-browser Coldcard Mk5 + Q1 simulator

A WebAssembly port of the Coldcard MicroPython firmware, rendered inside
Coldcard's own product photos. Sibling to [`cmd/coldcard-sim`](../coldcard-sim/),
not a replacement — the native unix-port simulator stays in the tree.
Both share `cmd/coldcard-sim/external/firmware/` and the product-photo
directory at `cmd/coldcard-sim/external/coldcard-photos/`.

Not affiliated with Coinkite Inc. Educational, non-commercial. See *License*
below.

## Layout

```
cmd/coldcard-wasm/
├── README.md                 ← this file
├── setup.sh                  ← fetches upstream MicroPython + emsdk (gitignored)
├── build.sh                  ← compiles each variant; stages photos
├── flake.nix                 ← nix devshell (optional; setup.sh works without nix)
├── index.html                ← standalone Mk5/Q1 device-frame page
├── variants/
│   ├── coldcard-mk5/         ← MicroPython webassembly variant (128×64 OLED)
│   └── coldcard-q1/          ← MicroPython webassembly variant (320×240 LCD)
├── test/smoke.mjs            ← headless Node smoke test for a built variant
├── assets/coldcard/          ← photos staged at build time (gitignored)
├── external/micropython/     ← upstream MicroPython @ pinned tag (gitignored)
└── emsdk/                    ← Emscripten SDK @ pinned version (gitignored)
```

Pinned versions (override via env):
- MicroPython: `v1.25.0` (`MICROPYTHON_REV`)
- Emscripten: `4.0.0` (`EMSCRIPTEN_REV`)
- Coldcard photos: SHA-256 pinned in `cmd/coldcard-sim/setup.sh`

## One-time setup

```sh
bash cmd/coldcard-sim/setup.sh    # firmware + product photos
bash cmd/coldcard-wasm/setup.sh   # micropython + emsdk (~700 MB, ~5 min)
```

If Emscripten 4.0.x produces a broken build, fall back to the LTS-ish
point release that upstream MicroPython and `@noble/curves` are known to
target:

```sh
EMSCRIPTEN_REV=3.1.74 bash cmd/coldcard-wasm/setup.sh
```

## Build & serve

```sh
bash cmd/coldcard-wasm/build.sh
python3 -m http.server 8782 -d cmd/coldcard-wasm
# open http://127.0.0.1:8782/
```

The page hosts both Mk5 and Q1 frames with a runtime selector
(URL hash `#mk5` / `#q1`). Variant selection persists in `localStorage`.

A headless smoke against the compiled module:

```sh
node cmd/coldcard-wasm/test/smoke.mjs coldcard-mk5
```

## Architecture

Two architectural decisions shape the build:

**MicroPython source — AD-1.** This port uses *vanilla upstream* MicroPython
at `v1.25.0`, not Coldcard's pinned fork. Coldcard's `mk3-peak-15-g4107246f8`
fork has a dead `ports/javascript/` (Emscripten fastcomp removed Aug 2020);
14/15 of Coldcard's MicroPython patches are stm32-only and irrelevant to
WebAssembly. Coldcard's `shared/` Python modules + `external/libngu/` C
crypto are pulled in as `USER_C_MODULES` variants. Nothing from Coldcard's
MicroPython fork is used.

**Crypto — AD-3 (Plan A inline contingency).** Plan A is libngu → WASM
(bundled secp256k1 v0.5.0 + cifra) compiled as `USER_C_MODULES` under
`ports/webassembly`. If the build exceeds 1.5 MB after `-O2 -DNDEBUG`,
or cifra inlining resists resolution within 2 pd, the contingency is
Plan B: a Python shim that dispatches into `@noble/curves` +
`@scure/bip32` via a hex-encoding JS bridge. Plan B is *inline in v1*,
not deferred — single timeline.

**JS↔Python bridge — AD-5.** Pattern B: Python owns
`uasyncio.run_forever()`. JS injects keycodes via `mp.pyimport('numpad')`;
Python writes NDEF bytes to MEMFS at `/work/nfc-dump.ndef`; JS reads via
`mp._module.FS.readFile()` and forwards into SeedHammer's engrave
pipeline through `window.seedhammerSynthTapText(text)`. Zero firmware
changes for the happy path.

**Filesystem — AD-4.** `/sd` and `/flash` are IDBFS-backed (persistent
across reloads — operators can drop PSBT files into the sim's "SD card"
and they survive refresh). `/work` is MEMFS (ephemeral — NDEF dump
buffer).

**Variant overlays — AD-6.** Each variant directory ships its own
`boot.py` with a `sys.modules['uasyncio'] = asyncio` shim (modern
MicroPython renamed `uasyncio` → `asyncio` around v1.21) and any
display/numpad/sim_nfc overlays under `shared_overrides/`. The shared
firmware tree at `cmd/coldcard-sim/external/firmware/shared/` is read
without modification.

## License

This directory's own files (`setup.sh`, `build.sh`, `flake.nix`,
`index.html`, `variants/*`, `test/*`, `README.md`) are under the
[Unlicense](../../LICENSE), same as the rest of SeedHammer.

`external/micropython/` is fetched by `setup.sh` from upstream
`micropython/micropython` and ships under MIT.

`emsdk/` is fetched by `setup.sh` and ships under MIT.

`assets/coldcard/*.png` are staged at build time from
`cmd/coldcard-sim/external/coldcard-photos/` (`mk5-front.png`,
`coldcard-q.png`). Product photography is © Coinkite Inc.; COLDCARD® is
a registered trademark. Use is educational and non-commercial; the
build-time fetch (never committed) makes any future takedown trivial —
delete the SHA-pinned fetch from `cmd/coldcard-sim/setup.sh` and the
page falls back to a stylised SVG placeholder. The page footer carries
the attribution boilerplate.

The Coldcard firmware tree under `cmd/coldcard-sim/external/firmware/`
ships under MIT + Commons Clause v1.0. The Commons Clause carves "Sell"
out of the otherwise-MIT grant; SeedHammer is Unlicense and not sold,
so the carve-out is not implicated. This simulator is educational and
does not custody real value.

## Relation to `cmd/coldcard-sim`

| | `cmd/coldcard-sim` | `cmd/coldcard-wasm` (this) |
|---|---|---|
| Backend | unix-port MicroPython (CPython host) | WebAssembly MicroPython (browser) |
| MicroPython | Coldcard's pinned fork | vanilla upstream `v1.25.0` |
| Driver | `bridge.py` WebSocket daemon | in-page `loadMicroPython` |
| Page | composer tab in `cmd/webnfc-sim` | standalone first, then integrated |
| Status | shipped 2026-05-15 | in progress |

Both ingest the same firmware tree and product photos; SeedHammer
consumes NDEF the same way regardless of source.
