// Headless smoke test for a built coldcard-mpy-<variant>.mjs. Verifies
// the runtime loads under Node and that libngu's ngu module imports — the
// minimal Phase 1 success signal per the plan.
//
//   node cmd/coldcard-wasm/test/smoke.mjs coldcard-mk5
//   node cmd/coldcard-wasm/test/smoke.mjs coldcard-q1

import { argv, exit } from "node:process";
import { pathToFileURL } from "node:url";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const variant = argv[2] || "coldcard-mk5";
const mjsPath = resolve(here, "..", `coldcard-mpy-${variant}.mjs`);

const mod = await import(pathToFileURL(mjsPath).href).catch((err) => {
  console.error(`load failed: ${mjsPath}`);
  console.error(err);
  exit(2);
});

const mp = await mod.loadMicroPython({
  heapsize: 4 * 1024 * 1024,
  stdout: (s) => process.stdout.write(s),
  stderr: (s) => process.stderr.write(s),
});

// Stub out the JS-callable mirror so seed_export's run() doesn't crash.
globalThis.coldcardMirror = (s) => { /* swallow */ };

mp.runPython(`
import sys
print("sys.version:", sys.version)
print("variant: ${variant}")

# D11 (DECISIONS-LOG): MVP build skips libngu; the demo path is
# the seed_export module which writes an NDEF Text record to MEMFS.
import seed_export
seed_export.on_key('1')

import os
st = os.stat('/work/nfc-dump.ndef')
print("ndef size:", st[6])

with open('/work/nfc-dump.ndef', 'rb') as f:
    data = f.read()
print("ndef hex:", "".join("%02x" % b for b in data[:16]), "...")
print("payload includes 'abandon':", b"abandon" in data)
print("SMOKE OK" if b"abandon" in data and st[6] > 30 else "SMOKE FAIL")
`);
