# Coldcard Mk5 WebAssembly variant — boot.
#
# AD-6: rename uasyncio → asyncio so Coldcard's shared/imptask.py and
# friends import cleanly under upstream MicroPython v1.21+ (where
# `uasyncio` was retired). The shim is variant-local; shared/ is not
# touched.
import asyncio as uasyncio
import sys
sys.modules['uasyncio'] = uasyncio

# Q1: flip the version flags that unix-sim version.py would have toggled
# via sys.argv ('--q1'). webassembly's sys module has no .argv, so we
# patch the flags after import. has_qwerty drives main.py's
# lcd_display vs display + FullKeyboard vs MembraneNumpad branches.
import version
version.has_qwerty = True
version.has_qr = True
version.num_sd_slots = 2
version.has_battery = True
version.supports_hsm = False
version.hw_label = 'q1'
version.mk_num = 4

# Skip the first-boot tamper-evidence + PIN dance: pre-load the
# unix-sim defaults that ship a "logged in, seed loaded" state. After
# this, main.py → more_setup → start_login_sequence → goto_top_menu
# lands straight on NormalSystem ("ready to sign"). The seed material
# is sim_settings' canonical _pin1_secret blob from the upstream tree.
import nvstore
from sim_settings import sim_defaults
nvstore.SettingsObject.default_values = lambda self: dict(sim_defaults)

# Modern MicroPython's asyncio.Loop dropped run_forever (the on-device
# Coldcard firmware uses it). Provide a shim that blocks on an infinite
# sleep task. We wrap get_event_loop to inject the method on every
# returned loop — assigning to Loop.run_forever directly doesn't bind
# self under MicroPython's slot-based type system.
if not hasattr(uasyncio.Loop, 'run_forever'):
    async def _forever_task():
        while True:
            await uasyncio.sleep(3600)

    # ASYNCIFY constraint: only one async operation in flight at a time.
    # The outer runPythonAsync that triggered "import main" is already
    # an async-paused ccall, so we cannot nest a sleep inside. Instead,
    # run_forever() just returns — the scheduled asyncio tasks (menu
    # loop, NFC handler, …) are already in the JS task queue and JS
    # keeps firing them via setTimeout. main.py raises RuntimeError
    # after run_forever returns; die_with_debug catches it. We swallow
    # that specific exception so the firmware doesn't paint "Yikes!!".
    class _LoopWrap:
        def __init__(self, real): self._real = real
        def run_forever(self):
            return None
        def __getattr__(self, n): return getattr(self._real, n)

    # main.py raises RuntimeError('main.stop') after our run_forever
    # shim returns; die_with_debug paints "Yikes!!" on the OLED for
    # that fatal exception. Swallow it so the menu screen stays.
    import imptask
    _orig_die = imptask.die_with_debug
    def _die_swallow_main_stop(exc):
        if isinstance(exc, RuntimeError) and str(exc) == 'main.stop':
            return
        return _orig_die(exc)
    imptask.die_with_debug = _die_swallow_main_stop

    _orig_gel = uasyncio.get_event_loop
    def _wrap_get_event_loop():
        return _LoopWrap(_orig_gel())
    uasyncio.get_event_loop = _wrap_get_event_loop

# Bridge module surface for shared/battery.py: it lazily imports
# machine.ADC inside get_batt_level(); unix/variant/machine.py doesn't
# expose ADC because the native sim never powers it up. Stub it out and
# short-circuit get_batt_level to "no battery / on USB power" so
# lcd_display.draw_status picks the plugged icon path.
import machine
class _SimADC:
    def __init__(self, *a, **k): pass
    def read(self): return 0
    def read_u16(self): return 0
machine.ADC = _SimADC

import battery as _battery
_battery.get_batt_level = lambda: None

# Pre-stage MEMFS directories that Coldcard's shared/mk4.py + shared/files.py
# expect — under emcc these aren't IDBFS-mounted yet, just normal MEMFS
# subdirs. mk4.init0() probes /flash via os.statvfs; pre-creating skips
# the make_flash_fs path that wants pyb.Flash() + os.VfsLfs2.mkfs.
import os
for d in ('/flash', '/flash/settings', '/sd', '/work', '/psram', '/psram/ident'):
    try:
        os.mkdir(d)
    except OSError:
        pass

# Coldcard's shared/files.py + shared/nvstore.py chdir into /flash. Match
# the on-device CWD so any relative-path operations resolve sanely.
try:
    os.chdir('/work')   # MEMFS scratch — nfc-dump.ndef lives here
except OSError:
    pass

# unix-sim's sim_nfc monkey-patches nfc.NFCHandler → SimulatedNFCHandler
# which writes NDEF tag images to ./nfc-dump.ndef (cwd-relative).
# Combined with the chdir to /work above, that's /work/nfc-dump.ndef —
# the file the JS-side polls and forwards to seedhammerSynthTapText.
try:
    import nfc as _nfc_mod
    import sim_nfc
    # sim_nfc.py rebinds its own local NFCHandler symbol but doesn't
    # touch the nfc module's class object. Patch it ourselves so
    # nfc.NFCHandler.startup() instantiates the sim variant.
    _nfc_mod.NFCHandler = sim_nfc.SimulatedNFCHandler
except ImportError:
    pass

# Pre-enable NFC in the simulated settings dict so actions.py's
# start_login_sequence wakes the handler. Without this, glob.NFC stays
# None and cc_share.share_seed_via_nfc fails.
sim_defaults['nfc'] = 1
