// Compile-time variant config for the Coldcard Q1 WebAssembly build.
//
// Q1 device profile:
//   - 320×240 colour LCD (graphics_q1.py packs RGB565 little-endian)
//   - Full QWERTY keyboard + 4-way nav + CANCEL/ENTER
//   - QR scanner, battery — both stubbed in shared_overrides/
//
// Heap sizing: 4 MB default. Q1's PSBT-signing working set is larger
// than Mk5's per "Open question #9"; tune up if Phase 2 surfaces OOMs.

#define MICROPY_VARIANT_ENABLE_JS_HOOK (1)

#define MICROPY_PY_ASYNCIO (1)
#define MICROPY_PY_UASYNCIO (0)

#define MICROPY_PY_RANDOM (0)

#define MICROPY_PY_DEFLATE (1)
#define MICROPY_PY_ZLIB (1)
#define MICROPY_GC_SPLIT_HEAP (1)
#define MICROPY_GC_SPLIT_HEAP_AUTO (1)
