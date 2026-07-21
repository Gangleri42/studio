# Coldcard Mk5 WebAssembly variant — minimum-viable seed-words export.
#
# D11 (DECISIONS-LOG): until libngu is rebased onto modern MicroPython's
# MP_DEFINE_CONST_OBJ_TYPE macro form, the variant ships without
# Coldcard's `shared/*.py` menu and without libngu. The demo path that
# the user can see end-to-end is: WASM → this module → NDEF Text record
# at /work/nfc-dump.ndef → JS forwards into window.seedhammerSynthTapText.
#
# Real Coldcard menu + libngu adaptation is follow-on work (Plan A
# completion). The contract with the SeedHammer engrave pipeline is the
# NDEF bytes, and they're identical regardless of the producer.

import os
import js


# Canonical 12-word BIP-39 test vector — matches the default in the
# combined sim's Coldcard Mk4 (sim) bridge tab and the Android shell.
TEST_VECTOR_12 = (
    "abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon abandon abandon about"
)
TEST_VECTOR_24 = (
    "abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon abandon abandon art"
)

_NFC_DUMP = '/work/nfc-dump.ndef'


def _build_ndef_text(text):
    # NDEF Type-2 tag image: CC bytes + TLV(0x03 len) + record + 0xFE.
    # Record: MB=1 ME=1 SR=1 TNF=0x01, type "T", payload = 0x02 "en" + utf-8.
    body = text.encode('utf-8')
    payload = bytes([0x02]) + b'en' + body
    record = bytearray()
    record.append(0xd1)  # MB=1 ME=1 CF=0 SR=1 IL=0 TNF=0x01
    record.append(0x01)  # type length
    record.append(len(payload) & 0xff)  # short-record payload length
    record.append(ord('T'))
    record += payload

    tlv = bytearray()
    if len(record) < 0xff:
        tlv += bytes([0x03, len(record)])
    else:
        tlv += bytes([0x03, 0xff, (len(record) >> 8) & 0xff, len(record) & 0xff])
    tlv += record
    tlv.append(0xfe)  # terminator

    # CC (capability container) bytes for NTAG-21x-style emulation.
    cc = bytes([0xe1, 0x10, 0x6d, 0x00])
    return cc + bytes(tlv)


def share_seed_words(words=None):
    text = words or TEST_VECTOR_12
    try:
        os.mkdir('/work')
    except OSError:
        pass
    payload = _build_ndef_text(text)
    with open(_NFC_DUMP, 'wb') as f:
        f.write(payload)
    print('[seed_export] wrote', len(payload), 'bytes to', _NFC_DUMP)
    return len(payload)


def _mirror(text):
    fn = getattr(js, 'coldcardMirror', None)
    if fn is not None:
        try:
            fn(text)
        except Exception:
            pass


def run():
    """Minimal menu driver: registers JS callbacks for the demo keys."""
    _mirror(
        'Coldcard Mk5 (WASM MVP)\n'
        '------------------\n'
        'Press 1 to export 12-word\n'
        'Press 2 to export 24-word\n'
        'Press x to clear'
    )


def on_key(key):
    # Driven from JS via mp.pyimport('seed_export').on_key('1')
    if key == '1':
        n = share_seed_words(TEST_VECTOR_12)
        _mirror('Shared 12-word seed via NFC ({} bytes).'.format(n))
    elif key == '2':
        n = share_seed_words(TEST_VECTOR_24)
        _mirror('Shared 24-word seed via NFC ({} bytes).'.format(n))
    elif key == 'x':
        _mirror('Cleared.')


run()
