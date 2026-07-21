#!/usr/bin/env bash
# Fetch modern upstream MicroPython (NOT Coldcard's fork) and the
# Emscripten SDK at pinned versions. Reference-only — nothing from
# upstream is committed in this repo. external/ and emsdk/ are
# gitignored.
#
# Usage:
#   bash cmd/coldcard-wasm/setup.sh
#
# Toolchain anchors (per plan-coldcard-wasm-frame-2026-05-16.md):
#   - AD-1: vanilla upstream MicroPython, not Coldcard's pinned fork
#           (Coldcard's mk3-peak-15-g4107246f8 has dead ports/javascript/).
#   - AD-2: Emscripten 4.0.x default; fall back to 3.1.74 if the smoke
#           build fails. Override with EMSCRIPTEN_REV=<tag>.
#
# Disk footprint: MicroPython ~150 MB; emsdk ~600 MB (cached).

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MPY_DEST="$HERE/external/micropython"
EMSDK_DEST="$HERE/emsdk"

MPY_REPO="${MICROPYTHON_REPO:-https://github.com/micropython/micropython}"
MPY_REV="${MICROPYTHON_REV:-v1.25.0}"

EMSCRIPTEN_REPO="${EMSCRIPTEN_REPO:-https://github.com/emscripten-core/emsdk}"
EMSCRIPTEN_REV="${EMSCRIPTEN_REV:-4.0.0}"

mkdir -p "$HERE/external"

have_working_repo() {
  git -C "$1" rev-parse --git-dir >/dev/null 2>&1
}

# --- MicroPython ---------------------------------------------------------
if have_working_repo "$MPY_DEST"; then
  current="$(git -C "$MPY_DEST" describe --tags --exact-match 2>/dev/null \
              || git -C "$MPY_DEST" rev-parse HEAD)"
  if [ "$current" = "$MPY_REV" ]; then
    echo "[setup] micropython already at $MPY_REV — skipping fetch"
  else
    echo "[setup] micropython at $current — updating to $MPY_REV"
    git -C "$MPY_DEST" fetch --tags --depth=1 origin "$MPY_REV"
    git -C "$MPY_DEST" checkout "$MPY_REV"
  fi
else
  echo "[setup] cloning $MPY_REPO at $MPY_REV"
  git clone --depth=1 --branch "$MPY_REV" "$MPY_REPO" "$MPY_DEST"
fi

# The webassembly port needs the micropython-lib snapshot for some
# frozen modules; submodule update is non-recursive.
echo "[setup] initialising micropython submodules (non-recursive)"
git -C "$MPY_DEST" submodule update --init -- lib/micropython-lib 2>/dev/null || true

# --- Emscripten SDK ------------------------------------------------------
if have_working_repo "$EMSDK_DEST"; then
  echo "[setup] emsdk already cloned"
else
  echo "[setup] cloning $EMSCRIPTEN_REPO"
  git clone --depth=1 "$EMSCRIPTEN_REPO" "$EMSDK_DEST"
fi

if [ ! -x "$EMSDK_DEST/emsdk" ]; then
  echo "error: $EMSDK_DEST/emsdk not executable after clone" >&2
  exit 2
fi

echo "[setup] installing emscripten $EMSCRIPTEN_REV"
"$EMSDK_DEST/emsdk" install "$EMSCRIPTEN_REV"
"$EMSDK_DEST/emsdk" activate "$EMSCRIPTEN_REV"

# Smoke check — version line should print without errors.
# shellcheck disable=SC1091
source "$EMSDK_DEST/emsdk_env.sh" >/dev/null 2>&1
emcc --version | head -1

echo "[setup] OK"
echo "[setup]   micropython: $MPY_DEST @ $(git -C "$MPY_DEST" describe --tags --always)"
echo "[setup]   emsdk:       $EMSDK_DEST @ $EMSCRIPTEN_REV"
echo "[setup] to enter the build env in this shell:"
echo "[setup]   source $EMSDK_DEST/emsdk_env.sh"
