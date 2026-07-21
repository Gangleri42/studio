// The NFC reader plumbing that turns a synthetic tap (a complete NDEF
// message pushed from JS) back into the byte stream the firmware's scan
// funnel expects. Kept free of the js build constraint so it is exercised
// by a host test: nfc_test.go proves a seedhammer.com:curves record taps
// through to a planned plate, the exact path the browser drives.

package main

import (
	"io"

	"seedhammer.com/nfc/ndef"
)

// ndefReader is the simulator-side equivalent of nfc/poller.Read's
// re-establish-on-EOF logic. Each tap delivers one complete NDEF
// message terminated by io.EOF; after that we discard the current
// readers and re-open fresh ones for the next tap.
//
// It surfaces RecordType so gui's scanner can dispatch typed records
// (see RecordType below); on hardware that role is filled by
// poller.Poller.
type ndefReader struct {
	nfc *nfcReader
	rr  *ndef.RecordReader
}

func (r *ndefReader) Read(buf []byte) (int, error) {
	for {
		if r.rr != nil {
			n, err := r.rr.Read(buf)
			if err != nil && (err != io.EOF || n == 0) {
				r.rr = nil
			}
			return n, err
		}
		r.rr = ndef.NewRecordReader(ndef.NewMessageReader(r.nfc))
	}
}

// RecordType surfaces the NDEF record type of the tap currently being
// delivered so gui's scanner (gui/scan.go) can dispatch typed records —
// specifically the seedhammer.com:curves external record the Studio
// editor sends. gui checks for this recordTyper interface right after a
// record's payload read returns io.EOF; without it every curves tap
// falls through to the content sniffer and is rejected as "Unknown
// format". The RecordReader keeps the type valid from the first payload
// read until the next record header is parsed, which is exactly that
// window. On the real device poller.Poller plays this part.
func (r *ndefReader) RecordType() []byte {
	if r.rr == nil {
		return nil
	}
	return r.rr.RecordType()
}

// Close unblocks a scanner goroutine parked in Read, exactly as closing the
// real poller does. StartScreen.Flow's cleanup does close(closer); r.Close();
// <-closed and will not return until the scanner exits — but the scanner is
// blocked in Read waiting for the next tap, and only Close can wake it. A
// no-op Close (the original) deadlocks Flow after the first scan, so the
// engrave flow never runs.
func (r *ndefReader) Close() error {
	r.nfc.close()
	return nil
}

// nfcReader is the io.Reader handed to gui.Run. Each "tap" delivers a complete
// NDEF byte stream and is terminated by io.EOF, after which the reader blocks
// until the next tap or until the current scan session is closed. Mirrors the
// on-device poller (see cmd/controller/platform_sh2.go:505) where Read blocks
// until a tag is detected and Close ends the session.
type nfcReader struct {
	taps    chan []byte
	done    chan struct{}
	current []byte
	hasMsg  bool
}

func newNFCReader() *nfcReader {
	return &nfcReader{taps: make(chan []byte, 1), done: make(chan struct{})}
}

// arm re-opens the reader for a new scan session, discarding the closed state
// of the previous one and any tap left buffered from it. StartScreen.Flow runs
// sequentially and its cleanup waits for the prior scanner to exit before the
// next Flow calls NFCReader, so there is never a live reader on the old done
// channel when this runs — but a tap the operator sent that the prior scanner
// never got to consume is still buffered, and must not auto-fire on the fresh
// scan screen, so drop it.
func (r *nfcReader) arm() {
	select {
	case <-r.done:
		r.done = make(chan struct{})
	default:
	}
	select {
	case <-r.taps:
	default:
	}
	r.hasMsg = false
	r.current = nil
}

func (r *nfcReader) close() {
	select {
	case <-r.done:
	default:
		close(r.done)
	}
}

func (r *nfcReader) Read(p []byte) (int, error) {
	if !r.hasMsg {
		select {
		case payload, ok := <-r.taps:
			if !ok {
				return 0, io.EOF
			}
			r.current = payload
			r.hasMsg = true
		case <-r.done:
			// Session closed while waiting for a tap; end the stream so
			// the scanner goroutine can observe its closer and exit.
			return 0, io.EOF
		}
	}
	if len(r.current) == 0 {
		r.hasMsg = false
		return 0, io.EOF
	}
	n := copy(p, r.current)
	r.current = r.current[n:]
	return n, nil
}

// tap queues a complete NDEF-wrapped payload, keeping only the latest. The
// scanner reads at most one tap per scan screen, so if one is still buffered
// (the firmware is off the scan screen, or hasn't consumed it yet) this drops
// the stale one in favour of the new payload — the last thing the operator
// sent is what the device reads, rather than the first. The channel has room
// for one, so after the drain the send never blocks.
func (r *nfcReader) tap(payload []byte) {
	select {
	case <-r.taps:
	default:
	}
	select {
	case r.taps <- payload:
	default:
	}
}
