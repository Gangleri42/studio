# Coldcard Q1 WebAssembly variant — ST7788 LCD with software GPU.
#
# Wraps a 320×240 RGB565 software framebuffer that JS reads from
# MEMFS /work/screen.bin (paint loop in app.js, little-endian RGB565).
# The on-device GPU coprocessor is replaced with pure-Python blit
# operations against this framebuffer; shared/lcd_display.py's show()
# loop, which paints menu text via show_pal_pixels and icons via
# show_zpixels, then renders pixel-identically to on-device.
#
# Wire formats — matched against unix/simulator.py's SDL paint path
# and shared/font_iosevka.py:
#
# * show_pal_pixels: 4-bit packed nibbles (high nibble first), continuous
#   across row boundaries, indexing a 32-byte palette of 16 RGB565 entries
#   stored big-endian (the on-wire SPI format used by shared/font_iosevka).
#
# * show_zpixels: raw-deflate compressed (wbits=-10) stream of
#   big-endian RGB565 pixel data, w*h pixels = w*h*2 bytes after inflate.
#
# * show_qr_data: 1-bit packed QR modules (MSB-first), scan_w bits per row
#   (scan_w = w rounded up to mod 8), exactly w rows. The output is
#   (w+2)*expand square: a 1-module white border on each side, each module
#   blown up to expand×expand. dark module bit (=1) → black, light bit → white.

import io
import struct

import deflate
import framebuf

WIDTH = 320
HEIGHT = 240


class _MockLED:
    bright = -1

    def intensity(self, n):
        self.bright = n

    def on(self):
        pass

    def off(self):
        pass


class ST7788:
    def __init__(self):
        self.backlight = _MockLED()
        self.fb = bytearray(WIDTH * HEIGHT * 2)
        self.gfx = framebuf.FrameBuffer(self.fb, WIDTH, HEIGHT, framebuf.RGB565)
        self._dirty()

    def _dirty(self):
        try:
            with open('/work/screen.bin', 'wb') as f:
                f.write(self.fb)
        except OSError:
            pass

    def gpu_send(self, cmd, *args):
        # On-device GPU command stream. The cursor/busy-bar animations
        # aren't modelled — keep as a no-op; cc_share and the menu paint
        # paths use the show_* primitives below.
        pass

    def fill_screen(self, pixel=0x0000):
        self.fill_rect(0, 0, WIDTH, HEIGHT, pixel)

    def fill_rect(self, x, y, w, h, pixel=0x0000):
        if w <= 0 or h <= 0:
            return
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        if x >= WIDTH or y >= HEIGHT:
            return
        if x + w > WIDTH:
            w = WIDTH - x
        if y + h > HEIGHT:
            h = HEIGHT - y
        lo = pixel & 0xff
        hi = (pixel >> 8) & 0xff
        fb = self.fb
        row = bytes((lo, hi)) * w
        rb = w * 2
        for ry in range(y, y + h):
            off = (ry * WIDTH + x) * 2
            fb[off:off + rb] = row
        self._dirty()

    def show_pal_pixels(self, x, y, w, h, palette, pixels):
        if w <= 0 or h <= 0 or x < 0 or y < 0:
            return
        if x + w > WIDTH or y + h > HEIGHT:
            # Glyphs occasionally overrun the right edge; clip rather than abort
            if x >= WIDTH or y >= HEIGHT:
                return
            cw = min(w, WIDTH - x)
            ch = min(h, HEIGHT - y)
        else:
            cw, ch = w, h

        # Build a 16-entry LE byte-pair LUT from the big-endian palette.
        pal = struct.unpack('>16H', palette)
        lut = []
        for p in pal:
            lut.append(bytes(((p & 0xff), ((p >> 8) & 0xff))))

        fb = self.fb
        nib_idx = 0
        rb = cw * 2
        for ry in range(h):
            if ry >= ch:
                # Still need to advance the nibble pointer to keep rows aligned.
                nib_idx += w
                continue
            parts = []
            base = nib_idx
            for col in range(w):
                byte = pixels[(base + col) >> 1]
                pix = (byte & 0xf) if ((base + col) & 1) else (byte >> 4)
                if col < cw:
                    parts.append(lut[pix])
            nib_idx += w
            row = b''.join(parts)
            off = ((y + ry) * WIDTH + x) * 2
            fb[off:off + rb] = row
        self._dirty()

    def show_zpixels(self, x, y, w, h, zpixels):
        if w <= 0 or h <= 0:
            return
        d = deflate.DeflateIO(io.BytesIO(zpixels), deflate.RAW, 10)
        raw = d.read()
        expect = w * h * 2
        if len(raw) < expect:
            return
        # raw is big-endian RGB565; swap to little-endian for our LE framebuffer.
        # struct.pack/unpack does the heavy lifting in C.
        n = w * h
        vals = struct.unpack('>%dH' % n, raw[:n * 2])
        swapped = struct.pack('<%dH' % n, *vals)
        if x < 0 or y < 0 or x + w > WIDTH or y + h > HEIGHT:
            # Clip to screen bounds row by row.
            cx = max(0, x)
            cy = max(0, y)
            cx_end = min(WIDTH, x + w)
            cy_end = min(HEIGHT, y + h)
            if cx >= cx_end or cy >= cy_end:
                return
            fb = self.fb
            src_x0 = cx - x
            src_y0 = cy - y
            cw = cx_end - cx
            for ry in range(cy, cy_end):
                src_off = ((src_y0 + (ry - cy)) * w + src_x0) * 2
                dst_off = (ry * WIDTH + cx) * 2
                fb[dst_off:dst_off + cw * 2] = swapped[src_off:src_off + cw * 2]
        else:
            fb = self.fb
            for ry in range(h):
                src_off = ry * w * 2
                dst_off = ((y + ry) * WIDTH + x) * 2
                fb[dst_off:dst_off + w * 2] = swapped[src_off:src_off + w * 2]
        self._dirty()

    def show_qr_data(self, x, y, w, expand, scan_w, packed_data, trim_lines=0):
        if w <= 0 or expand <= 0:
            return
        # scan_w may arrive as bytes per row or bits per row; rendered_qr_packed()
        # in moduqr.c returns sz = (w + 7) & ~7 — bits per row. Bytes/row:
        sw_bytes = scan_w // 8
        if sw_bytes * w != len(packed_data):
            # Defensive: if scan_w is already bytes (older callers), accept it.
            if scan_w * w == len(packed_data):
                sw_bytes = scan_w
            else:
                return

        W = (w + 2) * expand  # output square: 1-module border + QR area

        # trim_lines: drop up to that many of every-47th output row.
        delme = set()
        if trim_lines:
            cand = list(range(47, W, 47))
            delme = set(cand[:trim_lines])

        # Pre-compute the bit lookup per module x — avoids re-doing the
        # bit math in the inner loop.
        mod_bits = bytearray(w)

        fb = self.fb
        # Pre-built solid-color block bytes for one expand-wide pixel.
        black = bytes((0x00, 0x00)) * expand
        white = bytes((0xff, 0xff)) * expand

        oy = 0
        ry = y
        while oy < W and ry < HEIGHT:
            if oy in delme:
                oy += 1
                continue
            if ry < 0:
                oy += 1
                ry += 1
                continue
            qy = oy - expand
            if qy < 0 or qy >= w * expand:
                # full-width border row
                row = white * (w + 2)
            else:
                my = qy // expand
                # Cache module bits for this y
                row_off = my * sw_bytes
                # Build row: border + w modules + border
                parts = [white]
                for mx in range(w):
                    byte = packed_data[row_off + (mx >> 3)]
                    bit = (byte >> (7 - (mx & 7))) & 1
                    parts.append(black if bit else white)
                parts.append(white)
                row = b''.join(parts)

            # Clip horizontally
            if x < 0:
                row = row[(-x) * 2:]
                dst_x = 0
            else:
                dst_x = x
            avail = (WIDTH - dst_x) * 2
            if avail <= 0:
                oy += 1
                ry += 1
                continue
            if len(row) > avail:
                row = row[:avail]
            dst_off = (ry * WIDTH + dst_x) * 2
            fb[dst_off:dst_off + len(row)] = row

            oy += 1
            ry += 1
        self._dirty()

    def save_snapshot(self, full_path):
        # Not modelled — sim is screenshotted via the JS canvas instead.
        pass

# EOF
