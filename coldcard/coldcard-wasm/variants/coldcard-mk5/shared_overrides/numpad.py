# Coldcard Mk5 WebAssembly variant — numpad override.
#
# Replaces shared/numpad.py for the WASM build. The on-device version
# polls a row/column matrix over GPIO; under WASM, JS pushes key events
# into _queue via inject(), and the menu loop pulls from get_event().
#
# Per AD-5: keycodes flow JS → Python through this module.

import uasyncio as asyncio

# Coldcard's keycode table — single-char ASCII for digits, plus the
# special markers y / x / e / l / r used by shared/menu.py and friends.
KEY_OK     = 'y'
KEY_CANCEL = 'x'
KEY_ENTER  = 'e'
KEY_LEFT   = 'l'
KEY_RIGHT  = 'r'

_queue = []
_waiters = []


def inject(keycode):
    """Called by JS via mp.pyimport('numpad').inject(keycode)."""
    if not isinstance(keycode, str) or len(keycode) != 1:
        return
    _queue.append(keycode)
    if _waiters:
        ev = _waiters.pop(0)
        ev.set()


async def get_event():
    while not _queue:
        ev = asyncio.Event()
        _waiters.append(ev)
        await ev.wait()
    return _queue.pop(0), True


class Numpad:
    KEY_OK     = KEY_OK
    KEY_CANCEL = KEY_CANCEL
    KEY_ENTER  = KEY_ENTER
    KEY_LEFT   = KEY_LEFT
    KEY_RIGHT  = KEY_RIGHT

    def __init__(self):
        self.disabled = False

    def stop(self):
        self.disabled = True

    def start(self):
        self.disabled = False

    async def get(self):
        return await get_event()

    def empty(self):
        return not _queue

    def abort_ux(self):
        _queue.clear()

    def clear(self):
        _queue.clear()
