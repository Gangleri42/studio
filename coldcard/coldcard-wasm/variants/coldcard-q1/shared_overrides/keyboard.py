# Coldcard Q1 WebAssembly variant — FullKeyboard stub.
#
# Replaces shared/keyboard.py which polls a row/column QWERTY matrix
# via machine.Pin. Under WASM the JS side injects keycodes directly
# into NumpadBase._changes via FullKeyboard.inject() (the same canonical
# path the on-device hardware ISR feeds).

from numpad import NumpadBase


class FullKeyboard(NumpadBase):

    def __init__(self):
        super().__init__()

    def start(self):
        # No background poll task — JS drives the key queue.
        pass

    def stop(self):
        pass

    def shutdown(self):
        pass

    # NumpadBase.inject() is already the canonical key-event entrypoint.
    # FullKeyboard could override it on a real Q1 to mask out shift/sym
    # state, but for the demo the default NumpadBase.inject is enough.
