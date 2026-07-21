# Coldcard Q1 WebAssembly variant — display override.
#
# Replaces shared/lcd_display.py for the WASM build. Q1's on-device path
# drives a 320×240 colour LCD via the GPU coprocessor; under WASM we
# emit RGB565 little-endian pixel bytes to a JS callback. The page
# decodes RGB565 → RGBA on the canvas side.

import framebuf
import js

WIDTH = 320
HEIGHT = 240

_buf = bytearray(WIDTH * HEIGHT * 2)
_fb = framebuf.FrameBuffer(_buf, WIDTH, HEIGHT, framebuf.RGB565)


class Display:
    WIDTH = WIDTH
    HEIGHT = HEIGHT

    def __init__(self):
        self.dis = _fb

    def clear(self):
        _fb.fill(0)

    def show(self):
        try:
            with open('/work/screen.bin', 'wb') as f:
                f.write(bytes(_buf))
        except OSError:
            pass
        if hasattr(js, 'coldcardScreenPaint'):
            js.coldcardScreenPaint(bytes(_buf))

    def text(self, msg, x, y, c=0xffff, font=None):
        _fb.text(msg, x, y, c)

    def fill_rect(self, x, y, w, h, c):
        _fb.fill_rect(x, y, w, h, c)


def init():
    return Display()
