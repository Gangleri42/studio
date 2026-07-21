# Coldcard Mk5 WebAssembly variant — ckcc stub.
#
# Replaces the unix-sim ckcc.py whose constructor opens argv-passed
# file descriptors for the SDL-window LED pipe and NFC data pipe. Under
# WASM both those pipes are JS-side, not POSIX — we keep the API surface
# (gate, rng, vcp_enabled, …) but no descriptors.

import ustruct, sys, uasyncio, utime
from ubinascii import hexlify as b2a_hex

try:
    from uerrno import *
except ImportError:
    from errno import *

ERANGE = 34
ENOENT = 2
EPERM = 1

# WASM-side RNG: routed through MicroPython's getrandom-backed urandom.
import os
try:
    rng_fd = open('/dev/urandom', 'rb')
except OSError:
    rng_fd = None

genuine_led = True


class _NoopFile:
    def write(self, *a, **k): pass
    def read(self, *a, **k): return b''
    def close(self): pass

# unix machine.py expects ckcc.led_pipe to be writable for SD_ACTIVE,
# USB_ACTIVE, NFC_ACTIVE Pin transitions. WASM doesn't have the SDL
# window LED display so we swallow the writes.
led_pipe = _NoopFile()


class PSRAM:
    def __init__(self): pass
    def readblocks(self, *a, **k): pass
    def writeblocks(self, *a, **k): pass
    def ioctl(self, op, arg=None): return 0
    def wipe(self): pass


# Some Coldcard `shared/` modules import sim_secel directly.
try:
    from sim_secel import SEState
    SE_STATE = SEState()
except Exception:
    SE_STATE = None


def rng():
    if rng_fd is not None:
        return ustruct.unpack('I', rng_fd.read(4))[0] >> 2
    return ustruct.unpack('I', os.urandom(4))[0] >> 2


def rng_bytes(buf):
    if rng_fd is not None:
        actual = rng_fd.readinto(buf)
        assert actual == len(buf)
    else:
        data = os.urandom(len(buf))
        for i in range(len(buf)):
            buf[i] = data[i]


def pin_prefix(pin, buf_out):
    from uhashlib import sha256
    buf_out[0:4] = sha256(pin).digest()[0:4]
    return 0


def gate(method, buf_io, arg2):
    # Bootloader callgate — reproduces the unix sim's surface. Methods
    # 18 + 22 route to sim_secel + sim_se2 so PIN setup/login lands the
    # menu at NormalSystem (logged-in, seed-loaded) state.
    import version

    if method == 0:
        hc = b'2.0.0 time=20260516.000000 git=wasm@coldcard-mpy'
        buf_io[0:len(hc)] = hc
        return len(hc)
    if method == 5:
        return 0  # not bricked
    if method == 6:
        return ENOENT if not getattr(version, 'has_608', False) else 0
    if method == 18:
        # SE1 PIN stuff — routes to sim_secel.SEState
        if SE_STATE is not None:
            return SE_STATE.pin_stuff(arg2, buf_io)
        return ENOENT
    if method == 19:
        if arg2 == 0:
            buf_io[0:32] = b'CWASM000' + b'\0' * (32 - 8)
        if arg2 == 2:
            buf_io[0] = 2
        return 0
    if method == 21:
        if arg2 == 0:
            buf_io[0:8] = b'!\x03)\x19\'"\x00\x00'
        return 0
    if method == 22 and getattr(version, 'has_se2', False):
        # SE2 trick pin actions
        try:
            from sim_se2 import SE2
            return SE2.callgate(buf_io, arg2)
        except Exception:
            return ENOENT
    if method == 27:
        buf_io[:] = b'ATECC608B\nDS28C36B\0'
        return 0
    return ENOENT


def oneway(method, arg2):
    print("ckcc.oneway", method, arg2)
    while True:
        utime.sleep(60)


def is_simulator():
    return True


def is_debug_build():
    return True


def get_sim_root_dirs():
    return '/', '/MicroSD'


def presume_green():
    pass


def breakpoint():
    raise SystemExit


def watchpoint():
    pass


def vcp_enabled(_):
    return True


def usb_active():
    pass


def get_cpi_id():
    return 0x470  # STM32L4S5 (Mk4/Q1 chipset)


def lcd_blast(buf):
    pass
