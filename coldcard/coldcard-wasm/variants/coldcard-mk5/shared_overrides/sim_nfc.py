# Coldcard Mk5 WebAssembly variant — NFC export hook.
#
# Monkey-patches shared/nfc.py:NFCHandler.big_write so that NDEF tag
# images written by "Share Seed Words via NFC" land at MEMFS
# /work/nfc-dump.ndef, where the JS side picks them up via the
# Emscripten FS trackingDelegate and forwards into SeedHammer's
# engrave pipeline. Same path the v1 native sim takes
# (cmd/coldcard-sim/external/firmware/unix/variant/sim_nfc.py); just
# JS-readable instead of disk-readable.
#
# Per AD-5: Python writes the NDEF bytes; JS reads them.
import os
import nfc as _nfc_mod


_NFC_DUMP = '/work/nfc-dump.ndef'


def _wasm_big_write(self, ccfile_buf):
    try:
        os.mkdir('/work')
    except OSError:
        pass
    with open(_NFC_DUMP, 'wb') as f:
        f.write(bytes(ccfile_buf))


_nfc_mod.NFCHandler.big_write = _wasm_big_write
