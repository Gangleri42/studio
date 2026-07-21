# Coldcard Mk5 WebAssembly variant — uzlib compatibility shim.
#
# Modern MicroPython renamed extmod's uzlib → deflate (v1.22+). Coldcard
# firmware's shared/display.py + shared/graphics_mk4.py still call
# uzlib.decompress(data, wbits). This shim re-exports the legacy name.
import deflate
import io


def decompress(data, wbits=15):
    # wbits matches CPython zlib: negative → raw deflate, positive → zlib,
    # ≥31 → gzip. uzlib's wbits convention is the same.
    if wbits is None:
        wbits = 15
    if wbits < 0:
        fmt = deflate.RAW
        wbits = -wbits
    elif wbits >= 31:
        fmt = deflate.GZIP
        wbits = wbits - 16
    else:
        fmt = deflate.ZLIB
    buf = io.BytesIO(data)
    d = deflate.DeflateIO(buf, fmt, wbits)
    return d.read()


class DecompIO:
    def __init__(self, src, wbits=15):
        if wbits is None:
            wbits = 15
        if wbits < 0:
            fmt = deflate.RAW
            wbits = -wbits
        elif wbits >= 31:
            fmt = deflate.GZIP
            wbits = wbits - 16
        else:
            fmt = deflate.ZLIB
        self._d = deflate.DeflateIO(src, fmt, wbits)

    def read(self, n=-1):
        return self._d.read(n)

    def readline(self):
        return self._d.readline()

    def readinto(self, buf):
        return self._d.readinto(buf)
