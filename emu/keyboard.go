//go:build js && wasm

package main

import (
	"image"
	"syscall/js"

	"seedhammer.com/gui"
)

// installInputBridges registers the JS callbacks the host page uses to
// drive the emulator:
//
//   - seedhammerTouch(x, y, pressed) feeds canvas mouse/touch events as
//     gui.PointerEvent. SeedHammer II is a touch device, so this is the
//     only navigation input (mirrors processTouch in
//     cmd/controller/platform_sh2.go).
//   - seedhammerSynthTap(bytes) pushes a complete NDEF message onto the
//     tap queue, exactly as a scanned tag delivers it. Platform.NFCReader
//     parses it back through the production nfc/ndef readers, so the
//     firmware scan funnel runs unchanged. The host page builds the NDEF
//     message: a seedhammer.com:curves record for a Studio editor payload,
//     or a Well-Known Text record for a seed/descriptor/plain-text scan.
func installInputBridges(p *Platform) {
	js.Global().Set("seedhammerTouch", js.FuncOf(func(this js.Value, args []js.Value) any {
		if len(args) < 3 {
			return nil
		}
		p.events <- gui.PointerEvent{
			Pressed: args[2].Bool(),
			Entered: true,
			Pos:     image.Point{X: args[0].Int(), Y: args[1].Int()},
		}.Event()
		p.Wakeup()
		return nil
	}))

	js.Global().Set("seedhammerSynthTap", js.FuncOf(func(this js.Value, args []js.Value) any {
		if len(args) < 1 {
			return nil
		}
		n := args[0].Length()
		if n <= 0 {
			return nil
		}
		buf := make([]byte, n)
		js.CopyBytesToGo(buf, args[0])
		p.nfc.tap(buf)
		p.Wakeup()
		return nil
	}))
}
