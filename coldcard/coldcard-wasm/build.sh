#!/usr/bin/env bash
# Build the Coldcard WebAssembly simulator.
#
# Compiles each variant under cmd/coldcard-wasm/variants/ into a paired
# coldcard-mpy-<variant>.mjs + .wasm next to the static page, then stages
# the device-frame photos from cmd/coldcard-sim/external/coldcard-photos/.
#
# Prerequisites (run once, idempotent):
#   bash cmd/coldcard-sim/setup.sh    # photos + Coldcard firmware tree
#   bash cmd/coldcard-wasm/setup.sh   # upstream MicroPython + emsdk
#
# Per AD-2 (plan-coldcard-wasm-frame-2026-05-16.md): Emscripten 4.0.x
# default, fall back to 3.1.74 if the smoke build fails.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MPY="$HERE/external/micropython"
EMSDK="$HERE/emsdk"
# coldcard-sim is a sibling of coldcard-wasm, wherever this tree lives.
PHOTOS="$HERE/../coldcard-sim/external/coldcard-photos"

if [ ! -d "$MPY/ports/webassembly" ]; then
  echo "error: $MPY/ports/webassembly missing — run cmd/coldcard-wasm/setup.sh first" >&2
  exit 2
fi
if [ ! -d "$EMSDK" ]; then
  echo "error: $EMSDK missing — run cmd/coldcard-wasm/setup.sh first" >&2
  exit 2
fi

# shellcheck disable=SC1091
source "$EMSDK/emsdk_env.sh"

VARIANTS=("${COLDCARD_VARIANTS:-coldcard-mk5 coldcard-q1}")
# shellcheck disable=SC2206
VARIANTS=(${VARIANTS[*]})

# Pre-build mpy-cross at its DEFAULT path (mpy-cross/build/mpy-cross).
# The variant make below passes BUILD=build-$VARIANT, which the
# webassembly Makefile propagates into the mpy-cross sub-make — so the
# cross-compiler would otherwise land at mpy-cross/build-$VARIANT/
# while the frozen_content recipe expects it at mpy-cross/build/. One
# explicit build up-front puts the binary where the lookup expects it,
# and the variant sub-make then sees the target current and no-ops.
if [ ! -x "$MPY/mpy-cross/build/mpy-cross" ]; then
  echo "[build] pre-building mpy-cross at default BUILD path"
  make -C "$MPY/mpy-cross"
fi

# Each variant lives at variants/<name>/ with manifest.py, boot.py,
# mpconfigvariant.h, makefile.wasm. The makefile.wasm wraps MicroPython's
# ports/webassembly Makefile with USER_C_MODULES=libngu pointing into
# cmd/coldcard-sim/external/firmware/external/libngu (shared with the
# native simulator — single source of truth for the crypto).
for variant in "${VARIANTS[@]}"; do
  vdir="$HERE/variants/$variant"
  if [ ! -d "$vdir" ]; then
    echo "[build] skipping $variant — variants/$variant/ not present"
    continue
  fi
  echo "[build] $variant"
  make -C "$vdir" -f makefile.wasm
  # ports/webassembly Makefile hardcodes PROG=micropython; rename on stage
  # AND rewrite the .mjs's internal "micropython.wasm" reference so the
  # variant-prefixed .wasm is what the runtime fetches.
  build_dir="$MPY/ports/webassembly/build-$variant"
  install -m 644 "$build_dir/micropython.wasm" "$HERE/coldcard-mpy-$variant.wasm"
  sed -e "s/micropython\\.wasm/coldcard-mpy-$variant.wasm/g" \
      "$build_dir/micropython.mjs" > "$HERE/coldcard-mpy-$variant.mjs"
  mjs_size=$(stat -c%s "$HERE/coldcard-mpy-$variant.mjs")
  wasm_size=$(stat -c%s "$HERE/coldcard-mpy-$variant.wasm")
  echo "[build]   coldcard-mpy-$variant: .mjs $mjs_size B, .wasm $wasm_size B"
done

# Stage the photos for the standalone page. The webnfc-sim integration
# step (Phase 6) reuses these same files from the same source-of-truth
# directory; no duplication.
mkdir -p "$HERE/assets/coldcard"
for p in mk5-front.png coldcard-q.png; do
  if [ -f "$PHOTOS/$p" ]; then
    install -m 644 "$PHOTOS/$p" "$HERE/assets/coldcard/$p"
  fi
done

echo "[build] OK"
echo "[build] serve: python3 -m http.server 8782 -d $HERE"
