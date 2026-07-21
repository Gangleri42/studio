# Variant-specific build flags for Coldcard Mk5.
#
# Per AD-3 (plan-coldcard-wasm-frame-2026-05-16.md), Plan A inlines
# libngu (with bundled secp256k1 v0.5.0 + cifra) as USER_C_MODULES.
# Plan B contingency falls back to a Python shim dispatching into
# @noble/curves on the JS side. The makefile.wasm wrapper decides
# which path is active via COLDCARD_CRYPTO_PLAN.

JSFLAGS += -s ALLOW_MEMORY_GROWTH
JSFLAGS += -s INITIAL_MEMORY=16MB
JSFLAGS += -s STACK_SIZE=1048576
# No ASYNCIFY: the webassembly port's asyncio drives tasks via
# js.setTimeout(_run_iter, dt) — a JS-side scheduling primitive, not
# a Python-side block. Nothing in Coldcard's firmware actually needs
# to suspend a C call to await a JS Promise; ASYNCIFY just creates a
# nested-async conflict with proxy_c_to_js_call and bloats the .wasm
# by ~900 KB. Keeping it off lets the menu loop run.

# The frozen manifest pulls Coldcard's shared/ modules and a uasyncio
# shim from this variant's boot.py.
FROZEN_MANIFEST ?= $(VARIANT_DIR)/manifest.py
