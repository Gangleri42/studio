//go:build js && wasm

package main

import (
	"time"

	"seedhammer.com/gui"
)

// fakeEngraver returns a no-op session for every Platform.Engraver call.
// We are emulating, not driving steppers: the firmware's engrave loop feeds
// the planned step stream through Write; we accept it and discard it. The
// session sleeps in Close so the "Engraving plate" screen — showing the
// required time — stays visible long enough to screenshot before the UI
// transitions to the success state.
type fakeEngraver struct{}

func newFakeEngraver() *fakeEngraver { return &fakeEngraver{} }

func (e *fakeEngraver) open() (gui.Engraver, error) {
	return &fakeEngraverSession{}, nil
}

// displayHold is how long Close blocks before the engrave job is allowed to
// transition to engraveDone. Long enough for the operator to capture the
// running-state screen for the manual.
const displayHold = 5 * time.Second

type fakeEngraverSession struct{}

func (s *fakeEngraverSession) Write(words []uint32) (int, error) {
	return len(words), nil
}

func (s *fakeEngraverSession) Stats() gui.EngraverStats {
	return gui.EngraverStats{}
}

func (s *fakeEngraverSession) Close() error {
	time.Sleep(displayHold)
	return nil
}
