// Command wasmemu is a browser-based emulator of the SeedHammer II firmware
// GUI. It runs the unmodified gui package against a syscall/js Platform
// driver. The operator navigates the live touch UI; the host page feeds
// NFC taps (a seedhammer.com:curves record from Studio, or a text scan)
// via the seedhammerSynthTap global.
//
//go:build js && wasm

package main

import (
	"syscall/js"

	"seedhammer.com/gui"
)

func main() {
	blitter := js.Global().Get("seedhammerBlit")
	if blitter.IsUndefined() {
		// The HTML host did not register the canvas blitter.
		panic("wasmemu: seedhammerBlit is undefined; load index.html via a static server")
	}
	p := newPlatform(blitter)
	installInputBridges(p)
	for range gui.Run(p, "emu") {
	}
}
