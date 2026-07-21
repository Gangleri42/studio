#!/usr/bin/env bash
# Build the Coldcard firmware simulator (educational, non-official).
#
# Reference-only integration. Nothing from Coldcard/firmware is committed
# in this repo — setup.sh clones it at a pinned commit at first build.
# The resulting simulator is a CPython host driving coldcard-mpy
# (MicroPython unix-port with the Coldcard variant).
#
# Layout:
#   setup.sh                   — fetches Coldcard/firmware @ pinned SHA
#   build.sh                   — this script (apt-deps check + venv + build)
#   bridge.py                  — localhost WebSocket bridge (no firmware needed)
#   venv/                      — Python virtualenv (gitignored)
#   external/firmware/         — fetched at build time (gitignored)
#
# Run:
#   bash cmd/coldcard-sim/build.sh
#
# Apt prereqs (one-time, requires sudo):
#   sudo apt install -y libsdl2-dev libusb-1.0-0-dev libudev-dev \
#                       autoconf libtool python3-venv python3-dev

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$HERE/external/firmware"
VENV="$HERE/venv"

# Step 0: fetch the upstream firmware if not already on disk.
bash "$HERE/setup.sh"

if [ ! -d "$FW/unix" ]; then
  echo "error: $FW/unix not found after setup.sh — aborting" >&2
  exit 2
fi

# --- apt deps (check only; never install without explicit sudo from the user) ---
missing=()
for p in libsdl2-dev libusb-1.0-0-dev libudev-dev autoconf libtool python3-venv python3-dev; do
  if ! dpkg -s "$p" >/dev/null 2>&1; then
    missing+=("$p")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "error: missing apt packages: ${missing[*]}" >&2
  echo "       run: sudo apt install -y ${missing[*]}" >&2
  exit 3
fi

# --- venv ---
if [ ! -d "$VENV" ]; then
  echo "[build] creating venv $VENV"
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip wheel

# --- pin Ubuntu 24 micropython patch from upstream ---
if [ -f "$FW/ubuntu24_mpy.patch" ] && [ -d "$FW/external/micropython" ]; then
  if ! git -C "$FW/external/micropython" apply --check "$FW/ubuntu24_mpy.patch" 2>/dev/null; then
    echo "[build] ubuntu24_mpy.patch already applied"
  else
    echo "[build] applying ubuntu24_mpy.patch"
    git -C "$FW/external/micropython" apply "$FW/ubuntu24_mpy.patch"
  fi
fi

# --- Python requirements (Coldcard's superset + bridge deps) ---
echo "[build] installing python deps into venv"
# websockets <15 — v16's stricter handshake rejects Chrome's
# Connection: keep-alive, Upgrade header. v14 accepts it.
"$VENV/bin/pip" install --quiet pysdl2-dll PySDL2 Pillow 'websockets<15' watchdog || true
# Coldcard's full requirements.txt has internal -r refs; bring the unix subset.
"$VENV/bin/pip" install --quiet -r "$FW/unix/requirements.txt" 2>&1 | tail -5 || true

# --- mpy-cross ---
echo "[build] building mpy-cross"
make -C "$FW/external/micropython/mpy-cross" -j"$(nproc)" >/dev/null

# --- libngu (Coldcard's number-go-up crypto helper) ---
if [ ! -f "$FW/external/libngu/libngu.a" ] && [ ! -f "$FW/external/libngu/build/libngu.so" ]; then
  echo "[build] building libngu"
  (cd "$FW/external/libngu" && make min-one-time)
fi

# --- coldcard-mpy ---
echo "[build] building coldcard-mpy"
(cd "$FW/unix" && make setup) || true   # idempotent symlink setup
(cd "$FW/unix" && make ngu-setup) || true
(cd "$FW/unix" && PATH="$VENV/bin:$PATH" make -j"$(nproc)")

# --- sanity ---
if [ -x "$FW/unix/coldcard-mpy" ]; then
  echo "[build] OK — $FW/unix/coldcard-mpy"
  echo "[build] try: $FW/unix/simulator.py --mk4 --headless --eff -w"
else
  echo "[build] WARN — coldcard-mpy not found at $FW/unix/coldcard-mpy" >&2
  exit 4
fi
