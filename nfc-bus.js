// nfc-bus.js — the one place that turns a Studio editor payload into the
// exact byte stream a scanned tag delivers, and dispatches it to the
// in-browser SeedHammer emulator.
//
// The firmware recognises a drawing by its NDEF record type
// (seedhammer.com:curves, an external/TNF-0x04 record); everything else is
// content-sniffed. So the emulator must be fed a real NDEF message, not raw
// payload bytes. buildCurvesTap reproduces, byte-for-byte, what the
// nfc-bridge writes to a tag via ndeflib — proven by emu/nfc_test.go's
// golden and a node/ndeflib parity check. Both editor modes (text and path)
// travel as a curves record, matching the editor's own Web NFC send.
"use strict";
(function (root) {
  const RECORD_TYPE = "seedhammer.com:curves";
  const enc = new TextEncoder();

  // buildCurvesTap wraps a curves payload string as: an NDEF external record
  // of type seedhammer.com:curves, inside an NDEF-message TLV
  // (0x03 <len> … 0xFE) — the layer the firmware's nfc/ndef reader parses.
  // Short vs long forms follow the NFC Forum spec exactly (SR when the
  // payload fits a byte, 0xFF-escaped 2-byte TLV length past 254), so the
  // output equals ndeflib's for every size.
  function buildCurvesTap(payloadStr) {
    const payload = enc.encode(payloadStr);
    const type = enc.encode(RECORD_TYPE); // 21 bytes, ASCII
    const rec = [];
    if (payload.length < 256) {
      // MB | ME | SR | TNF-external, 1-byte payload length.
      rec.push(0xd4, type.length, payload.length);
    } else {
      // MB | ME | TNF-external, 4-byte payload length.
      const n = payload.length;
      rec.push(0xc4, type.length, (n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255);
    }
    for (const b of type) rec.push(b);
    for (const b of payload) rec.push(b);

    const tlv = [];
    if (rec.length < 255) {
      tlv.push(0x03, rec.length);
    } else {
      tlv.push(0x03, 0xff, (rec.length >>> 8) & 255, rec.length & 255);
    }
    for (const b of rec) tlv.push(b);
    tlv.push(0xfe);
    return new Uint8Array(tlv);
  }

  // buildTextTap wraps plain text as an NDEF Well-Known Text record inside a
  // message TLV — the byte shape a scanned seed or descriptor tag carries.
  // The Coldcard emulator exports a seed/descriptor as text; the SeedHammer
  // firmware content-sniffs it (bip39 / descriptor / codex32 / plain text),
  // so it must arrive as a Text record, not a curves record.
  function buildTextTap(text) {
    const body = enc.encode(text);
    const payload = new Uint8Array(3 + body.length);
    payload[0] = 0x02; // UTF-8, language length 2
    payload[1] = 0x65; // 'e'
    payload[2] = 0x6e; // 'n'
    payload.set(body, 3);
    const rec = [];
    if (payload.length < 256) {
      rec.push(0xd1, 0x01, payload.length, 0x54); // MB|ME|SR|WellKnown, type "T"
    } else {
      const n = payload.length;
      rec.push(0xc1, 0x01, (n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255, 0x54);
    }
    for (const b of payload) rec.push(b);
    const tlv = [];
    if (rec.length < 255) {
      tlv.push(0x03, rec.length);
    } else {
      tlv.push(0x03, 0xff, (rec.length >>> 8) & 255, rec.length & 255);
    }
    for (const b of rec) tlv.push(b);
    tlv.push(0xfe);
    return new Uint8Array(tlv);
  }

  // feedEmu delivers a curves payload to the running emulator as a synthetic
  // tap. Returns false if the emulator isn't booted yet (its tap global is
  // installed by the wasm main), so callers can defer.
  function feedEmu(payloadStr) {
    if (typeof root.seedhammerSynthTap !== "function") return false;
    root.seedhammerSynthTap(buildCurvesTap(payloadStr));
    return true;
  }

  // feedEmuText delivers plain text (a Coldcard seed/descriptor export) to the
  // emulator as a Well-Known Text tap.
  function feedEmuText(text) {
    if (typeof root.seedhammerSynthTap !== "function") return false;
    root.seedhammerSynthTap(buildTextTap(text));
    return true;
  }

  root.NFCBus = { RECORD_TYPE, buildCurvesTap, buildTextTap, feedEmu, feedEmuText };
})(typeof globalThis !== "undefined" ? globalThis : this);
