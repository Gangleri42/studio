#!/usr/bin/env bash
# Fetch the Coldcard firmware at the pinned commit if it's not already
# present. Reference-only — nothing from upstream is committed in this
# repo. The directory is .gitignored.
#
# Usage:
#   bash cmd/coldcard-sim/setup.sh            # idempotent: skips if rev matches
#   COLDCARD_REV=<sha> bash cmd/coldcard-sim/setup.sh    # override pin
#
# Disk footprint of a fresh setup is ~250 MB (firmware + the submodules
# the unix simulator actually needs). NEVER use --recursive at the
# top-level: it drags pico-sdk / tinyusb / nrfx — multi-GB STM32-only
# trees the unix build never touches. We init only the submodules
# directly needed for the unix port.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/external/firmware"
REPO="${COLDCARD_REPO:-https://github.com/Coldcard/firmware}"
REV="${COLDCARD_REV:-ca06dfd2509eacfad333be9d35ed274559915d0e}"   # 2026-03-05  v5.5.0-26

# Submodules the upstream unix/ build actually needs. Everything else
# (pico-sdk, tinyusb, nrfx, STM32 HAL, ...) is for the on-device builds
# we don't run. Coldcard's own unix/Makefile setup target only runs a
# non-recursive `git submodule update --init` inside micropython, which
# is the right size.
NEEDED_FIRMWARE_SUBMODULES=(
  external/micropython
  external/libngu
  external/ckcc-protocol
  external/c-modules
  external/mpy-qr
)

mkdir -p "$HERE/external"

have_working_repo() {
  git -C "$DEST" rev-parse --git-dir >/dev/null 2>&1
}

if have_working_repo; then
  current="$(git -C "$DEST" rev-parse HEAD 2>/dev/null || echo unknown)"
  if [ "$current" = "$REV" ]; then
    echo "[setup] firmware already at $REV — skipping clone"
  else
    echo "[setup] firmware at $current — updating to $REV"
    git -C "$DEST" fetch --tags origin "$REV"
    git -C "$DEST" checkout "$REV"
  fi
elif [ -d "$DEST" ] && [ "$(ls -A "$DEST" 2>/dev/null)" ]; then
  # Directory has content but no working .git (possibly a dangling gitlink
  # file from a previous submodule deinit). Wipe any broken gitlink, init
  # a fresh repo, fetch the pin, and hard-reset so the working tree matches.
  echo "[setup] adopting existing $DEST (no working git repo, has content)"
  rm -f "$DEST/.git"   # broken gitlink file, if any
  git -C "$DEST" init -q
  git -C "$DEST" remote add origin "$REPO" 2>/dev/null || git -C "$DEST" remote set-url origin "$REPO"
  git -C "$DEST" fetch --depth=1 --tags origin "$REV"
  git -C "$DEST" reset --hard "$REV"
else
  echo "[setup] cloning $REPO at $REV"
  git clone "$REPO" "$DEST"
  git -C "$DEST" checkout "$REV"
fi

# Direct submodules (non-recursive). One pass; idempotent.
echo "[setup] initialising needed firmware submodules (non-recursive)"
git -C "$DEST" submodule update --init -- "${NEEDED_FIRMWARE_SUBMODULES[@]}"

# libngu's own submodules — hand-picked, NOT --recursive. The three below
# carry headers that libngu's source files include directly:
#   libs/secp256k1  → lib_secp256k1.c #include "secp256k1/include/secp256k1.h"
#   libs/cifra      → hm.c, aes.c #include "cifra/{hmac,modes}.h"
#   libs/bech32     → codecs.c, lib_segwit.c #include "bech32/segwit_addr.{h,c}"
# Explicitly skipped: libs/mpy (duplicates external/micropython, ~150 MB +
# 14 nested submodules) and libs/esp-idf (~250 MB, ESP32-only, unused by
# the mk5/q1 WASM build).
echo "[setup] initialising libngu's bundled-crypto submodules"
git -C "$DEST/external/libngu" submodule update --init -- \
  libs/secp256k1 libs/cifra libs/bech32

# Inside micropython, the unix port has its own setup that pulls the
# small subset of submodules the unix port actually compiles. Coldcard's
# own unix/Makefile setup target handles this — invoked from build.sh.

# Coldcard product photos: Studio renders an ORIGINAL device frame and never
# ships Coinkite trade dress, so the photo fetch is OFF by default. Opt in with
# COLDCARD_FETCH_PHOTOS=1 (the standalone native simulator uses them). Trade
# dress is © Coinkite Inc. The libngu patches below run either way — they gate
# the wasm build and must not be skipped along with the photos.
if [ "${COLDCARD_FETCH_PHOTOS:-0}" = "1" ]; then
  PHOTOS_DIR="$HERE/external/coldcard-photos"
  mkdir -p "$PHOTOS_DIR"

  fetch_photo() {
    local name="$1" want_sha="$2"
    local out="$PHOTOS_DIR/$name"
    if [ -f "$out" ]; then
      local have_sha
      have_sha="$(sha256sum "$out" | cut -d' ' -f1)"
      if [ "$have_sha" = "$want_sha" ]; then
        echo "[setup] photo $name already at $want_sha — skipping"
        return 0
      fi
      echo "[setup] photo $name sha mismatch ($have_sha) — refetching"
    fi
    echo "[setup] fetching $name from coldcard.com"
    curl -fsSL "https://coldcard.com/static/images/$name" -o "$out.tmp"
    local got_sha
    got_sha="$(sha256sum "$out.tmp" | cut -d' ' -f1)"
    if [ "$got_sha" != "$want_sha" ]; then
      rm -f "$out.tmp"
      echo "error: $name sha mismatch — want $want_sha got $got_sha" >&2
      exit 5
    fi
    mv "$out.tmp" "$out"
  }

  fetch_photo mk5-front.png  7df45c7b4f1508467faef120e9eef16f7990c6d8b3b95c25a238da3c425f4713
  fetch_photo coldcard-q.png 661ff4d51f485bfbfe378d9bf2066bc2eba94e91209e61c30fc4eb48135fb0da
  echo "[setup] photos at $PHOTOS_DIR"
else
  echo "[setup] skipping Coldcard product photos (Studio uses an original frame)"
fi

# Apply libngu compatibility overlay for modern MicroPython (v1.21+)
# so cmd/coldcard-wasm/build.sh succeeds against upstream's renamed
# m_new_obj_var, removed STATIC macro, vanished extmod/crypto-algorithms,
# the mp_obj_new_str_from_vstr split, and clang's typeof rejection in
# -std=c99. The patch + companion sha256_compat.h shim are tracked in
# cmd/coldcard-wasm/patches/ (libngu/ itself stays gitignored).
LIBNGU="$DEST/external/libngu"
PATCH_DIR="$(cd "$HERE/../coldcard-wasm/patches" 2>/dev/null && pwd || true)"
if [ -n "$PATCH_DIR" ] && [ -f "$PATCH_DIR/libngu-modern-mpy.patch" ] && [ -d "$LIBNGU" ]; then
  # Reset libngu's tracked files to its pinned commit before applying.
  # A cached/restored libngu may carry a previously-applied version of
  # this patch; without reset, `git apply --check` fails on context
  # mismatch and we'd silently skip the patch on subsequent CI runs.
  # Submodule contents (libs/secp256k1, libs/cifra, libs/bech32) are
  # gitlinks and survive `checkout -- .`.
  git -C "$LIBNGU" checkout -- . 2>/dev/null || true
  if git -C "$LIBNGU" apply --check "$PATCH_DIR/libngu-modern-mpy.patch" 2>/dev/null; then
    echo "[setup] applying libngu modern-mpy compat patch"
    git -C "$LIBNGU" apply "$PATCH_DIR/libngu-modern-mpy.patch"
  else
    echo "[setup] libngu modern-mpy patch fails apply-check — refusing to silently skip"
    git -C "$LIBNGU" apply --check "$PATCH_DIR/libngu-modern-mpy.patch"
    exit 1
  fi
  if [ -f "$PATCH_DIR/sha256_compat.h" ]; then
    install -m 644 "$PATCH_DIR/sha256_compat.h" "$LIBNGU/ngu/sha256_compat.h"
  fi
fi

# libngu ships its own bech32 compat patch at libngu/bech32.patch — it
# makes the static `convert_bits` external and adds the declaration to
# segwit_addr.h, which ngu/codecs.c and ngu/lib_segwit.c both need at
# compile time. libngu's Makefile defines BECH32_PATCH as a hook but
# never calls it from any recipe (it expects a parent build system to
# invoke it). Apply it here, idempotently, mirroring the libngu-modern
# pattern above. Reset bech32's tracked tree first so a cached restore
# can't block re-application.
BECH32="$LIBNGU/libs/bech32"
if [ -f "$LIBNGU/bech32.patch" ] && { [ -d "$BECH32/.git" ] || [ -f "$BECH32/.git" ]; }; then
  git -C "$BECH32" checkout -- . 2>/dev/null || true
  if git -C "$BECH32" apply --check "$LIBNGU/bech32.patch" 2>/dev/null; then
    echo "[setup] applying libngu bech32 compat patch (convert_bits extern)"
    git -C "$BECH32" apply "$LIBNGU/bech32.patch"
  else
    echo "[setup] libngu bech32 patch fails apply-check — refusing to silently skip"
    git -C "$BECH32" apply --check "$LIBNGU/bech32.patch"
    exit 1
  fi
fi

echo "[setup] OK — $DEST @ $(git -C "$DEST" rev-parse --short HEAD)"
