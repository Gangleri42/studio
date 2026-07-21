# Frozen-module manifest for the Coldcard Mk5 WebAssembly variant.
#
# v1 surface = boot.py (uasyncio shim) + the shared_overrides JS
# bridge stubs + libngu's bundled `bip39.py`. Coldcard's `shared/*.py`
# (mk4.py, glob.py, callgate.py, …) imports `machine`/`pyb`/`ckcc`
# directly; importing them under WebAssembly needs a per-symbol stub
# pass that's tracked as Phase-1 follow-on work. The current frozen
# set lets `import ngu` work and provides the boot harness that
# follow-on shared/ adaptation iterates against.

freeze('.', 'boot.py')
freeze('.', 'seed_export.py')
freeze('.', 'cc_share.py')

# WebAssembly-specific shared/ overrides — freeze BEFORE the unix
# variant + Coldcard shared/ trees so these win the import-name race.
freeze('shared_overrides', 'pyb.py')
freeze('shared_overrides', 'ckcc.py')
freeze('shared_overrides', 'uzlib.py')
freeze('shared_overrides', 'ssd1306.py')

# Phase 2: Coldcard shared/*.py tree adapted via the unix-port simulator's
# hardware stubs (machine, pyb, ckcc, sim_*, ssd1306, …). The full
# upstream firmware tree is in cmd/coldcard-sim/external/firmware/; we
# freeze the unix variant's stubs first so the real shared/ modules see
# them when they try to import machine/pyb/ckcc.
#
# Manifest variable interpolation only resolves $(MPY_DIR)/$(PORT_DIR)/
# $(BOARD_DIR)/$(MPY_LIB_DIR), so we anchor to $(PORT_DIR) and walk back
# to seedhammer's cmd/coldcard-sim/external/firmware/.
COLDCARD_FW = '$(PORT_DIR)/../../../../../coldcard-sim/external/firmware/shared'
COLDCARD_VARIANT = '$(PORT_DIR)/../../../../../coldcard-sim/external/firmware/unix/variant'

# Hardware stubs from unix/variant — same shape Coldcard's native sim uses.
freeze(COLDCARD_VARIANT, 'aes256ctr.py')
# ckcc.py: shadowed by shared_overrides/ckcc.py (no SDL-window fd plumbing)
freeze(COLDCARD_VARIANT, 'ffilib.py')
freeze(COLDCARD_VARIANT, 'machine.py')
freeze(COLDCARD_VARIANT, 'mock.py')
# pyb.py: shadowed by shared_overrides/pyb.py (no socket plumbing under WASM)
freeze(COLDCARD_VARIANT, 'sim_battery.py')
freeze(COLDCARD_VARIANT, 'sim_mk4.py')
freeze(COLDCARD_VARIANT, 'sim_nfc.py')
freeze(COLDCARD_VARIANT, 'sim_psram.py')
freeze(COLDCARD_VARIANT, 'sim_quickstart.py')
freeze(COLDCARD_VARIANT, 'sim_se2.py')
freeze(COLDCARD_VARIANT, 'sim_secel.py')
freeze(COLDCARD_VARIANT, 'sim_settings.py')
freeze(COLDCARD_VARIANT, 'sim_vdisk.py')
freeze(COLDCARD_VARIANT, 'stm.py')
freeze(COLDCARD_VARIANT, 'version.py')

# Coldcard shared/ firmware. The unix sim's manifest.py is the canonical
# list; we freeze the bulk and let imports drive any further trimming.
freeze(COLDCARD_FW, 'public_constants.py')
freeze(COLDCARD_FW, 'sigheader.py')
freeze(COLDCARD_FW, 'charcodes.py')
freeze(COLDCARD_FW, 'glob.py')
freeze(COLDCARD_FW, 'imptask.py')
freeze(COLDCARD_FW, 'h.py')
freeze(COLDCARD_FW, 'mk4.py')
freeze(COLDCARD_FW, 'mempad.py')
# shared/ssd1306.py: shadowed by shared_overrides/ssd1306.py
freeze(COLDCARD_FW, 'display.py')
freeze(COLDCARD_FW, 'numpad.py')
freeze(COLDCARD_FW, 'queues.py')
freeze(COLDCARD_FW, 'callgate.py')
freeze(COLDCARD_FW, 'psram.py')
freeze(COLDCARD_FW, 'random.py')
freeze(COLDCARD_FW, 'nvstore.py')
freeze(COLDCARD_FW, 'utils.py')
freeze(COLDCARD_FW, 'files.py')
freeze(COLDCARD_FW, 'opcodes.py')
freeze(COLDCARD_FW, 'choosers.py')
freeze(COLDCARD_FW, 'actions.py')
freeze(COLDCARD_FW, 'flow.py')
freeze(COLDCARD_FW, 'history.py')
freeze(COLDCARD_FW, 'ftux.py')
freeze(COLDCARD_FW, 'login.py')
freeze(COLDCARD_FW, 'paper.py')
freeze(COLDCARD_FW, 'pincodes.py')
freeze(COLDCARD_FW, 'seed.py')
freeze(COLDCARD_FW, 'stash.py')
freeze(COLDCARD_FW, 'sffile.py')
freeze(COLDCARD_FW, 'serializations.py')
freeze(COLDCARD_FW, 'wif.py')
freeze(COLDCARD_FW, 'chains.py')
freeze(COLDCARD_FW, 'msgsign.py')
freeze(COLDCARD_FW, 'ndef.py')
freeze(COLDCARD_FW, 'nfc.py')
freeze(COLDCARD_FW, 'auth.py')
freeze(COLDCARD_FW, 'address_explorer.py')
freeze(COLDCARD_FW, 'export.py')
freeze(COLDCARD_FW, 'backups.py')
freeze(COLDCARD_FW, 'descriptor.py')
freeze(COLDCARD_FW, 'multisig.py')
freeze(COLDCARD_FW, 'wallet.py')
freeze(COLDCARD_FW, 'ownership.py')
freeze(COLDCARD_FW, 'qrs.py')
freeze(COLDCARD_FW, 'compat7z.py')
freeze(COLDCARD_FW, 'drv_entro.py')
freeze(COLDCARD_FW, 'tapsigner.py')
freeze(COLDCARD_FW, 'trick_pins.py')
freeze(COLDCARD_FW, 'users.py')
freeze(COLDCARD_FW, 'web2fa.py')
freeze(COLDCARD_FW, 'xor_seed.py')
freeze(COLDCARD_FW, 'hsm.py')
freeze(COLDCARD_FW, 'hsm_ux.py')
freeze(COLDCARD_FW, 'ccc.py')
freeze(COLDCARD_FW, 'countdowns.py')
freeze(COLDCARD_FW, 'psbt.py')
freeze(COLDCARD_FW, 'pwsave.py')
freeze(COLDCARD_FW, 'vdisk.py')
freeze(COLDCARD_FW, 'callgate.py' if False else 'selftest.py')
freeze(COLDCARD_FW, 'dev_helper.py')
freeze(COLDCARD_FW, 'menu.py')
freeze(COLDCARD_FW, 'ux.py')
freeze(COLDCARD_FW, 'ux_mk4.py')
freeze(COLDCARD_FW, 'graphics_mk4.py')
freeze(COLDCARD_FW, 'zevvpeep.py')
freeze(COLDCARD_FW, 'exceptions.py')
freeze(COLDCARD_FW, 'main.py')

include('$(PORT_DIR)/variants/manifest.py')
