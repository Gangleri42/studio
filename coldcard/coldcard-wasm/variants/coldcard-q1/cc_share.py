# Coldcard Mk5 WebAssembly variant — direct NFC seed/descriptor share.
#
# JS-callable shortcuts that bypass the menu chain and emit the same
# NDEF tag image to MEMFS /work/nfc-dump.ndef that the user would get
# by navigating Advanced/Tools → Danger Zone → Seed Functions → View
# Seed Words → "3" for NFC. Same Coldcard `shared/nfc.py:NFCHandler.share_text`
# code path; same byte-for-byte output as on-device hardware.
#
# Usage from JS:
#   mp.runPython("import cc_share; cc_share.share_seed_via_nfc()")
#   mp.runPython("import cc_share; cc_share.share_descriptor_via_nfc()")
# The result lands at /work/nfc-dump.ndef; the page polls and forwards
# into window.seedhammerSynthTapText.

import asyncio


def _kick(coro):
    """Schedule a coroutine onto the live asyncio loop without awaiting."""
    asyncio.create_task(coro)


async def _share_seed_via_nfc():
    import stash
    from glob import NFC
    import bip39  # libngu frozen module

    with stash.SensitiveValues(bypass_tmp=False, enforce_delta=True) as sv:
        if sv.mode != 'words':
            print('cc_share: wallet is not word-based, mode=', sv.mode)
            return
        words = bip39.b2a_words(bytes(sv.raw))
    print('cc_share: sharing', len(words.split()), 'seed words via NFC')
    # NFC.share_text writes the NDEF tag image; sim_nfc.py overlay
    # redirects NFCHandler.big_write to MEMFS /work/nfc-dump.ndef.
    await NFC.share_text(words, is_secret=True)
    print('cc_share: seed shared.')


async def _share_descriptor_via_nfc():
    from glob import NFC
    from chains import current_chain
    import stash

    # single-sig default-account descriptor at m/84h/coin_type'/0h
    with stash.SensitiveValues() as sv:
        chain = current_chain()
        n = sv.derive_path("m/84h/%dh/0h" % chain.b44_cointype)
        xpub = chain.serialize_public(n)
        xfp = sv.get_xfp()
    desc = "wpkh([%08x/84h/%dh/0h]%s/<0;1>/*)" % (xfp, chain.b44_cointype, xpub)
    print('cc_share: sharing descriptor', desc[:60], '…')
    await NFC.share_text(desc)
    print('cc_share: descriptor shared.')


def share_seed_via_nfc():
    _kick(_share_seed_via_nfc())


def share_descriptor_via_nfc():
    _kick(_share_descriptor_via_nfc())
