# Coldcard Q1 WebAssembly variant — NFC export hook.
#
# Identical shape to the Mk5 variant — NDEF tag image lands at MEMFS
# /work/nfc-dump.ndef on every "Share … via NFC" menu invocation.
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
