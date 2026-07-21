# Coldcard Q1 WebAssembly variant — GPU coprocessor stub.
#
# Replaces shared/gpu.py which talks to the on-device GPU over I2C
# (machine.I2C(1, freq=400000)) and feeds it cursor/busy-bar animations.
# Under WASM we render everything via the software-GPU primitives in
# st7788.py; the GPU class only needs to expose the API surface used by
# shared/lcd_display.py and the Advanced/Tools menu.

class GPUAccess:
    def __init__(self):
        self.i_have_spi = True

    def reset(self):
        pass

    def get_version(self):
        return 'WASM'

    def take_spi(self):
        # Returns True if the GPU previously had SPI control (i.e. an
        # animation was running). We never animate, so always False.
        was_busy = not self.i_have_spi
        self.i_have_spi = True
        return was_busy

    def give_spi(self):
        self.i_have_spi = False

    def have_spi(self):
        return self.i_have_spi

    def busy_bar(self, enable):
        # The bar would animate via the on-device GPU; we just track state.
        self.i_have_spi = not enable

    def cursor_off(self):
        self.i_have_spi = True

    def cursor_at(self, x, y, cur_type):
        # Menu cursor / cell highlight. Not rendered in this sim — the
        # menu's invert-attribute on the selected row gives a usable
        # visual highlight via show_pal_pixels.
        self.i_have_spi = False

    def show_test_pattern(self):
        pass

    def upgrade(self):
        return 'WASM'

    def upgrade_if_needed(self):
        return

    async def reflash_gpu_ux(self):
        return

# EOF
