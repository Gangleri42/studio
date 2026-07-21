# Coldcard Mk5 WebAssembly variant — pyb stub.
#
# Replaces the unix-sim pyb.py (which binds to a UNIX domain socket to
# talk to an external SDL window). Under WebAssembly the firmware is
# already inside the renderer (canvas), so the socket plumbing is dead
# weight. Provides USB_VCP/USB_HID/Pin/LED/Timer/ADC dummies — enough
# for shared/*.py to import and call into without crashing.

import time

SOCKET_FILE_PATH = None


class USB_VCP:
    @staticmethod
    def isconnected(): return False

    @staticmethod
    def any(): return False

    @staticmethod
    def read(*a, **k): return b''

    @staticmethod
    def write(*a, **k): pass


_umode = None
UNSET = object()


def usb_mode(nm=UNSET, **kws):
    global _umode
    if nm is not UNSET:
        _umode = nm
    return _umode


class USB_HID:
    def __init__(self): pass
    def recv(self, buf, timeout=0): return 0
    def send(self, msg): pass


class Pin:
    OUT = 0
    IN = 1
    PULL_UP = 0
    PULL_DOWN = 0
    PULL_NONE = 0

    def __init__(self, *a, **k): self._v = 0
    def value(self, v=None):
        if v is None: return self._v
        self._v = v
    def init(self, *a, **k): pass
    def on(self): self._v = 1
    def off(self): self._v = 0
    def __call__(self, *a, **k): return self.value(*a, **k)


class LED:
    def __init__(self, *a, **k): pass
    def on(self): pass
    def off(self): pass
    def toggle(self): pass
    def intensity(self, *a): pass


class Timer:
    UP = 0; DOWN = 1; OUT_COMPARE = 0; PWM = 0
    def __init__(self, *a, **k): pass
    def init(self, *a, **k): pass
    def callback(self, *a, **k): pass
    def deinit(self): pass


class ADC:
    def __init__(self, *a, **k): pass
    def read(self): return 0
    def read_u16(self): return 0


class SPI:
    MASTER = 0; SLAVE = 1; MSB = 0; LSB = 1
    def __init__(self, *a, **k): pass
    def init(self, *a, **k): pass
    def read(self, n, *a): return b'\x00' * n
    def write(self, *a, **k): pass


class I2C:
    MASTER = 0
    def __init__(self, *a, **k): pass
    def init(self, *a, **k): pass


def delay(ms): time.sleep_ms(ms)
def udelay(us): time.sleep_us(us)
def millis(): return time.ticks_ms()
def micros(): return time.ticks_us()


def unique_id():
    return b'COLDCARD-WASM-SIM'


def freq(*a):
    return 168000000


def hard_reset():
    raise SystemExit('hard_reset')


def soft_reset():
    raise SystemExit('soft_reset')


def disable_irq(): return False
def enable_irq(state=True): pass


def wfi(): pass
def stop(): pass
def standby(): pass


class RTC:
    def __init__(self, *a, **k): pass
    def datetime(self, *a):
        if a: return
        return (2026, 5, 16, 6, 12, 0, 0, 0)


class ExtInt:
    IRQ_RISING = 0
    IRQ_FALLING = 1
    IRQ_RISING_FALLING = 2
    PULL_UP = 0
    PULL_DOWN = 1
    PULL_NONE = 2

    def __init__(self, *a, **k): pass
    def enable(self): pass
    def disable(self): pass
    def line(self): return 0
    def swint(self): pass


class Flash:
    def __init__(self, *a, **k): pass
    def readblocks(self, *a, **k): pass
    def writeblocks(self, *a, **k): pass
    def ioctl(self, op, arg=None): return 0


class SD:
    def __init__(self, *a, **k): pass
    def present(self): return False
    def power(self, on): pass
