# Coldcard Q1 WebAssembly variant — keyboard override.
#
# Q1 uses shared/keyboard.py to drive a 4×4 nav row + full QWERTY plus
# SHIFT/SYM modifiers. Under WASM the JS side pushes the resulting
# character into _queue via inject(); the menu loop pulls it as if it
# came from the physical matrix scan.
#
# Numpad.KEY_* constants stay compatible with shared/menu.py and
# shared/ux.py so the integration point is identical to the Mk5 variant.

import uasyncio as asyncio

KEY_OK     = 'y'
KEY_CANCEL = 'x'
KEY_ENTER  = '\r'
KEY_LEFT   = 'l'
KEY_RIGHT  = 'r'
KEY_UP     = '\x0b'
KEY_DOWN   = '\x0a'

# JS-side data-key mnemonics → firmware charcodes (shared/charcodes.py).
# Keep the friendly mnemonics ('u', 'd') in the HTML attributes so the
# markup stays readable; translate at the inject boundary.
_KEY_REMAP = {
    'u': KEY_UP,
    'd': KEY_DOWN,
}

_queue = []
_waiters = []


def inject(keycode):
    if not isinstance(keycode, str) or not keycode:
        return
    for ch in keycode:
        _queue.append(_KEY_REMAP.get(ch, ch))
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

    def stop(self):  self.disabled = True
    def start(self): self.disabled = False

    async def get(self):
        return await get_event()

    def empty(self):
        return not _queue

    def abort_ux(self):
        _queue.clear()

    def clear(self):
        _queue.clear()
