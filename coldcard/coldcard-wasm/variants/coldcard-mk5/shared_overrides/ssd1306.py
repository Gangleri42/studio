# Coldcard Mk5 WebAssembly variant — SSD1306 OLED stub.
#
# Replaces unix-sim's ssd1306.py (which opens an argv-passed file
# descriptor to push framebuffer bytes into the SDL window). The WASM
# variant just keeps the bytes in a Python bytearray and posts them
# to window.coldcardScreenPaint on every show().

import framebuf
import js


class SSD1306(framebuf.FrameBuffer):
    def __init__(self, width, height, is_mk5):
        self.width = width
        self.height = height
        self.is_mk5 = is_mk5
        self.pages = self.height // 8
        self.buffer = bytearray(self.pages * self.width)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def init_display(self):
        self.fill(0)
        self.show()

    def write_cmd(self, cmd):
        pass

    def write_data(self, buf):
        pass

    def poweroff(self): pass
    def poweron(self): pass
    def contrast(self, c): pass
    def invert(self, v): pass

    def show(self):
        # Snapshot the framebuffer to MEMFS — JS polls /work/screen.bin
        # at 50 ms and unpacks MONO_VLSB → canvas pixels. Going only
        # through the FS sidesteps the ASYNCIFY "nested async" assertion
        # that triggers when proxy_c_to_js_call sees a JS callback
        # during the parent runPythonAsync ccall.
        try:
            with open('/work/screen.bin', 'wb') as f:
                f.write(self.buffer)
        except OSError:
            pass

    def busy_bar(self, enable, pattern):
        if enable:
            self.buffer[-len(pattern):] = pattern
            self.show()


class SSD1306_SPI(SSD1306):
    def __init__(self, width, height, spi, dc, res, cs, is_mk5=False):
        super().__init__(width, height, is_mk5)
