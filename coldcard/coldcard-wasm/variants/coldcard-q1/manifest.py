# Frozen-module manifest for the Coldcard Q1 WebAssembly variant.
#
# Mirrors the Mk5 manifest with Q1-specific swaps: q1.py replaces mk4.py,
# graphics_q1 replaces graphics_mk4, lcd_display replaces display,
# keyboard.py replaces mempad. The unix-sim's hardware stubs cover the
# common ground; Q1-specific WASM overlays (lcd_display, st7788, keyboard)
# replace the SDL-window-bound or hardware-driver-bound originals.

freeze('.', 'boot.py')
freeze('.', 'seed_export.py')
freeze('.', 'cc_share.py')

# WebAssembly-specific shared/ overrides — frozen first so they win the
# import-name race against the unix variant + Coldcard shared/ trees.
freeze('shared_overrides', 'pyb.py')
freeze('shared_overrides', 'ckcc.py')
freeze('shared_overrides', 'uzlib.py')
freeze('shared_overrides', 'st7788.py')
freeze('shared_overrides', 'gpu.py')
freeze('shared_overrides', 'keyboard.py')

COLDCARD_FW = '$(PORT_DIR)/../../../../../coldcard-sim/external/firmware/shared'
COLDCARD_VARIANT = '$(PORT_DIR)/../../../../../coldcard-sim/external/firmware/unix/variant'

# Hardware stubs from unix/variant — same shape Coldcard's native sim uses.
freeze(COLDCARD_VARIANT, 'aes256ctr.py')
# ckcc.py: shadowed by shared_overrides/ckcc.py
freeze(COLDCARD_VARIANT, 'ffilib.py')
freeze(COLDCARD_VARIANT, 'machine.py')
freeze(COLDCARD_VARIANT, 'mock.py')
# pyb.py: shadowed by shared_overrides/pyb.py
freeze(COLDCARD_VARIANT, 'sim_battery.py')
freeze(COLDCARD_VARIANT, 'sim_mk4.py')
freeze(COLDCARD_VARIANT, 'sim_nfc.py')
freeze(COLDCARD_VARIANT, 'sim_psram.py')
freeze(COLDCARD_VARIANT, 'sim_quickstart.py')
freeze(COLDCARD_VARIANT, 'sim_se2.py')
freeze(COLDCARD_VARIANT, 'sim_secel.py')
freeze(COLDCARD_VARIANT, 'sim_settings.py')
freeze(COLDCARD_VARIANT, 'sim_vdisk.py')
# ssd1306 is Mk5-only — not used on Q1
freeze(COLDCARD_VARIANT, 'stm.py')
freeze(COLDCARD_VARIANT, 'version.py')

# Coldcard shared/ firmware — Q1 variant module set.
freeze(COLDCARD_FW, 'public_constants.py')
freeze(COLDCARD_FW, 'sigheader.py')
freeze(COLDCARD_FW, 'charcodes.py')
freeze(COLDCARD_FW, 'glob.py')
freeze(COLDCARD_FW, 'imptask.py')
freeze(COLDCARD_FW, 'h.py')
freeze(COLDCARD_FW, 'mk4.py')             # also imported by Q1's flow.py
freeze(COLDCARD_FW, 'q1.py')              # Q1-specific
freeze(COLDCARD_FW, 'graphics_q1.py')     # Q1-specific
freeze(COLDCARD_FW, 'font_iosevka.py')    # Q1-specific (only Q1 has this font)
freeze(COLDCARD_FW, 'battery.py')         # Q1 has battery
# gpu.py replaced by shared_overrides/gpu.py — on-device shared/gpu.py
# wants machine.I2C and a real GPU coprocessor over the bus.
freeze(COLDCARD_FW, 'gpu_binary.py')
freeze(COLDCARD_FW, 'lcd_display.py')     # the real Q1 LCD renderer
# display.py is Mk5-only (SSD1306). Q1 imports lcd_display instead.
# keyboard.py replaced by shared_overrides/keyboard.py
freeze(COLDCARD_FW, 'numpad.py')          # NumpadBase used by FullKeyboard
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
freeze(COLDCARD_FW, 'selftest.py')
freeze(COLDCARD_FW, 'dev_helper.py')
freeze(COLDCARD_FW, 'decoders.py')        # Q1-specific (QR decoder dispatch)
freeze(COLDCARD_FW, 'scanner.py')
freeze(COLDCARD_FW, 'notes.py')
freeze(COLDCARD_FW, 'bbqr.py')
freeze(COLDCARD_FW, 'teleport.py')
freeze(COLDCARD_FW, 'menu.py')
freeze(COLDCARD_FW, 'ux.py')
freeze(COLDCARD_FW, 'ux_q1.py')           # Q1-specific
freeze(COLDCARD_FW, 'exceptions.py')
freeze(COLDCARD_FW, 'main.py')

include('$(PORT_DIR)/variants/manifest.py')
