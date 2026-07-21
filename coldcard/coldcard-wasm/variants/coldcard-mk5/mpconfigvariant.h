// Compile-time variant config for the Coldcard Mk5 WebAssembly build.
//
// Per AD-1 (plan-coldcard-wasm-frame-2026-05-16.md), this variant lives
// under upstream MicroPython's ports/webassembly/variants/ — the on-disk
// path is set by the variants/coldcard-mk5/makefile.wasm shim, which
// drops a sibling directory inside the upstream tree at build time and
// points VARIANT_DIR at it.
//
// Mk5 device profile:
//   - 128×64 mono OLED (graphics_mk4.py shares Mk4 framebuffer format)
//   - 12-key numeric pad + OK/Cancel
//   - microSD slot, USB-C, NFC over PN532 — modelled in shared_overrides/
//
// Heap sizing per "Open question #9": 4 MB default, tuned in Phase 2.

#define MICROPY_VARIANT_ENABLE_JS_HOOK (1)

// Coldcard's shared/imptask.py drives a uasyncio loop with multiple
// concurrent tasks. Upstream ports/webassembly turns this on by default;
// re-stating for documentation.
#define MICROPY_PY_ASYNCIO (1)
#define MICROPY_PY_UASYNCIO (0)

// B13: libngu exports its own mp_module_random; turn off the upstream
// random module to avoid a duplicate-symbol link error. Coldcard's
// shared/*.py and libngu's bip39.py both go through ngu.random.
#define MICROPY_PY_RANDOM (0)

// B18: shared/display.py + shared/graphics_mk4.py decompress font assets
// via uzlib. Modern MicroPython renames the module to `deflate`; a
// shared_overrides/uzlib.py shim re-exposes the legacy name.
#define MICROPY_PY_DEFLATE (1)
#define MICROPY_PY_ZLIB (1)

// Without ASYNCIFY, MicroPython's stm32-style gc_collect() that walks
// emscripten_scan_registers errors out. The split-heap-auto variant
// uses a different GC path that doesn't need register scanning —
// suited for the browser-driven event loop where GC happens between
// JS task scheduler ticks, not in the middle of a function.
#define MICROPY_GC_SPLIT_HEAP (1)
#define MICROPY_GC_SPLIT_HEAP_AUTO (1)
