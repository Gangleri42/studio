package main

import (
	"bytes"
	"encoding/binary"
	"encoding/hex"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"seedhammer.com/bip39"
	"seedhammer.com/curves"
	"seedhammer.com/engrave"
)

// gateParams mirrors the emulator's engraverParams (platform.go, js-tagged
// and so invisible here) closely enough to exercise the curves planner: the
// editor emits a "1 path 100 30" header, and the stroke-width check in
// curves.Parse only passes when Millimeter/StrokeWidth match that 100 units/mm,
// 30-unit-wide stroke — i.e. 6400 machine units/mm and a 0.3 mm needle.
const gateMM = 6400

var gateParams = engrave.Params{
	StrokeWidth: 0.3 * gateMM,
	Millimeter:  gateMM,
	StepperConfig: engrave.StepperConfig{
		TicksPerSecond: 30 * gateMM,
		Speed:          30 * gateMM,
		EngravingSpeed: 8 * gateMM,
		Acceleration:   250 * gateMM,
		Jerk:           2600 * gateMM,
	},
}

// buildCurvesTap wraps a curves payload the way the Studio host does before
// handing it to seedhammerSynthTap: a single NDEF external record of type
// "seedhammer.com:curves", inside an NDEF-message TLV (0x03 len … 0xFE). This
// is the reference implementation; nfc-bus.js reproduces it byte-for-byte
// (guarded by the node parity check and the ndeflib cross-check), so the emu
// sees exactly what the bench-proven bridge writes to a tag.
func buildCurvesTap(payload []byte) []byte {
	typ := []byte(curves.RecordType) // "seedhammer.com:curves"
	var rec []byte
	if len(payload) < 256 {
		// Short record: MB|ME|SR|TNF-external, 1-byte payload length.
		rec = append(rec, 0x80|0x40|0x10|0x04, byte(len(typ)), byte(len(payload)))
	} else {
		// Long record: MB|ME|TNF-external, 4-byte payload length.
		rec = append(rec, 0x80|0x40|0x04, byte(len(typ)))
		rec = binary.BigEndian.AppendUint32(rec, uint32(len(payload)))
	}
	rec = append(rec, typ...)
	rec = append(rec, payload...)

	var tlv []byte
	if len(rec) < 255 {
		tlv = append(tlv, 0x03, byte(len(rec)))
	} else {
		tlv = append(tlv, 0x03, 0xFF)
		tlv = binary.BigEndian.AppendUint16(tlv, uint16(len(rec)))
	}
	tlv = append(tlv, rec...)
	tlv = append(tlv, 0xFE)
	return tlv
}

// A path payload the editor's emit() would produce for a square drawn
// inside the plate (10 mm … 75 mm), coordinates quantized at 100 units/mm.
const pathPayload = "1 path 100 30\n" +
	"M1000 1000 L7500 1000 L7500 7500 L1000 7500 L1000 1000"

const textPayload = "1 text\nIN CASE OF EMERGENCY\nBREAK GLASS"

// TestCurvesTapRecognized is the correctness gate the whole hub hinges on:
// a curves tap must be *recognized as curves* by the emulator's reader, not
// fall through to the content sniffer. It drives the exact reader the emu
// hands gui (ndefReader over nfcReader), asserts the record type dispatches,
// the payload round-trips, and the curves planner accepts it within caps.
func TestCurvesTapRecognized(t *testing.T) {
	tap := buildCurvesTap([]byte(pathPayload))

	nr := newNFCReader()
	nr.tap(tap)
	r := &ndefReader{nfc: nr}

	got, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("read tap: %v", err)
	}
	// The recordTyper contract gui/scan.go relies on. Without ndefReader
	// exposing this, a curves tap is rejected as "Unknown format".
	if rt := string(r.RecordType()); rt != curves.RecordType {
		t.Fatalf("record type = %q, want %q", rt, curves.RecordType)
	}
	if !bytes.Equal(got, []byte(pathPayload)) {
		t.Fatalf("payload round-trip mismatch:\n got %q\nwant %q", got, pathPayload)
	}

	// The scan funnel would now hand these bytes to the curves planner.
	d, err := curves.Parse(got, gateParams)
	if err != nil {
		t.Fatalf("curves.Parse: %v", err)
	}
	rep, err := d.Validate(gateParams)
	if err != nil {
		t.Fatalf("curves.Validate: %v", err)
	}
	if d.Strokes == 0 || d.Knots == 0 {
		t.Fatalf("planned an empty drawing: %+v", d)
	}
	if d.Strokes > curves.MaxStrokes || d.Knots > curves.MaxKnots {
		t.Fatalf("drawing exceeds caps: %+v", d)
	}
	t.Logf("planned: strokes=%d knots=%d report=%+v", d.Strokes, d.Knots, rep)
}

// TestTextTapRoundTrips proves the text-mode payload also survives the wrap:
// text records go through the same curves external record (the editor sends
// SH.recordType for both modes), and the firmware's Text() reads the body.
func TestTextTapRoundTrips(t *testing.T) {
	tap := buildCurvesTap([]byte(textPayload))
	nr := newNFCReader()
	nr.tap(tap)
	r := &ndefReader{nfc: nr}

	got, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("read tap: %v", err)
	}
	if rt := string(r.RecordType()); rt != curves.RecordType {
		t.Fatalf("record type = %q, want %q", rt, curves.RecordType)
	}
	if mode, err := curves.Mode(got); err != nil || mode != curves.ModeText {
		t.Fatalf("mode = %q, %v; want text", mode, err)
	}
	body, err := curves.Text(got)
	if err != nil {
		t.Fatalf("curves.Text: %v", err)
	}
	if body != "IN CASE OF EMERGENCY\nBREAK GLASS" {
		t.Fatalf("text body = %q", body)
	}
}

// TestLongCurvesTap exercises the >255-byte payload path: a long NDEF record
// (SR clear, 4-byte payload length) inside a long message TLV (0xFF-escaped
// 2-byte length). The Studio Rich tab produces payloads in the tens of KB, so
// this size is the common case, not an edge one.
func TestLongCurvesTap(t *testing.T) {
	var b strings.Builder
	b.WriteString("1 path 100 30\nM1000 1000")
	for i := 0; i < 400; i++ { // ~400 line segments → several KB, well past 255
		fmt.Fprintf(&b, " L%d %d", 1000+(i%50)*100, 1000+(i%40)*100)
	}
	payload := b.String()
	if len(payload) < 256 {
		t.Fatalf("payload not long enough to test the long-record path: %d", len(payload))
	}
	tap := buildCurvesTap([]byte(payload))

	nr := newNFCReader()
	nr.tap(tap)
	r := &ndefReader{nfc: nr}
	got, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("read long tap: %v", err)
	}
	if rt := string(r.RecordType()); rt != curves.RecordType {
		t.Fatalf("long record type = %q, want %q", rt, curves.RecordType)
	}
	if string(got) != payload {
		t.Fatalf("long payload round-trip mismatch (%d vs %d bytes)", len(got), len(payload))
	}
	if _, err := curves.Parse(got, gateParams); err != nil {
		t.Fatalf("curves.Parse(long): %v", err)
	}
}

// buildTextTap mirrors nfc-bus.js buildTextTap: a Well-Known Text record in a
// message TLV, the byte shape the Coldcard transport delivers a seed or
// descriptor as.
func buildTextTap(text string) []byte {
	payload := append([]byte{0x02, 'e', 'n'}, text...)
	var rec []byte
	if len(payload) < 256 {
		rec = append(rec, 0xd1, 0x01, byte(len(payload)), 'T')
	} else {
		rec = append(rec, 0xc1, 0x01)
		rec = binary.BigEndian.AppendUint32(rec, uint32(len(payload)))
		rec = append(rec, 'T')
	}
	rec = append(rec, payload...)
	var tlv []byte
	if len(rec) < 255 {
		tlv = append(tlv, 0x03, byte(len(rec)))
	} else {
		tlv = append(tlv, 0x03, 0xFF)
		tlv = binary.BigEndian.AppendUint16(tlv, uint16(len(rec)))
	}
	tlv = append(tlv, rec...)
	tlv = append(tlv, 0xFE)
	return tlv
}

// TestColdcardSeedTapContentSniffs is the Coldcard→SeedHammer transport gate:
// the Coldcard exports a seed as a space-separated BIP39 mnemonic in an NDEF
// Text record. The emu reader must decode it to plain text (record type empty,
// so the scan funnel content-sniffs it) and bip39.Parse must accept it — the
// path that lands on the backup-wallet flow.
func TestColdcardSeedTapContentSniffs(t *testing.T) {
	const seed = "abandon abandon abandon abandon abandon abandon " +
		"abandon abandon abandon abandon abandon about"
	tap := buildTextTap(seed)

	nr := newNFCReader()
	nr.tap(tap)
	r := &ndefReader{nfc: nr}
	got, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("read text tap: %v", err)
	}
	// A Well-Known Text record is decoded, not passed through: the reader
	// yields the body and reports no record type, so the scan funnel sniffs it.
	if rt := r.RecordType(); len(rt) != 0 {
		t.Fatalf("text record should surface no type, got %q", rt)
	}
	if string(got) != seed {
		t.Fatalf("text body = %q, want %q", got, seed)
	}
	if _, err := bip39.Parse(got); err != nil {
		t.Fatalf("bip39.Parse of the Coldcard seed export: %v", err)
	}
}

// updateGolden regenerates the testdata fixtures instead of asserting against
// them: `go test -run TestGoldenTaps -update`.
var updateGolden = flag.Bool("update", false, "rewrite the golden tap fixtures")

// TestGoldenTaps guards the reference tap bytes the JS builder (node parity
// check) and the ndeflib writer (python cross-check) diff against. By default
// it ASSERTS the committed fixtures still match what buildCurvesTap emits, so a
// byte-encoding change fails here rather than silently rewriting the golden the
// parity checks then validate against. `-update` rewrites them.
func TestGoldenTaps(t *testing.T) {
	dir := "testdata"
	fixtures := map[string]string{
		"tap_path.hex": pathPayload,
		"tap_text.hex": textPayload,
	}
	if *updateGolden {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
		for name, p := range fixtures {
			b := hex.EncodeToString(buildCurvesTap([]byte(p))) + "\n"
			if err := os.WriteFile(filepath.Join(dir, name), []byte(b), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		return
	}
	for name, p := range fixtures {
		want, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			t.Fatalf("read golden %s: %v (regenerate with `go test -run TestGoldenTaps -update`)", name, err)
		}
		got := hex.EncodeToString(buildCurvesTap([]byte(p))) + "\n"
		if got != string(want) {
			t.Errorf("%s drifted from the committed golden:\n got %s\nwant %s", name, got, want)
		}
	}
}
