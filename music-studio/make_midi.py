#!/usr/bin/env python3
"""Generate the starter MIDI pack: 130 BPM, A minor.

Those two numbers are not arbitrary — they come from the audio features of
Bicep's "Opal" (130 BPM, A minor, Camelot 8A, danceability 0.80), used here as
the reference for the melodic-house sound this project is aiming at.

Writes four single-track type-0 files into ./midi. No dependencies; the MIDI
bytes are assembled by hand.

    python3 make_midi.py
"""

import os
import struct

PPQ = 480          # ticks per quarter note
BPM = 130
BARS = 8
BEATS_PER_BAR = 4

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midi")

# vi - IV - I - V in A minor, one chord per bar, voiced around the octave above
# middle C so there is room for a bassline underneath without clashing.
PROGRESSION = [
    ("Am9",   [57, 60, 64, 71]),   # A3  C4  E4  B4
    ("Fmaj9", [53, 57, 60, 67]),   # F3  A3  C4  G4
    ("Cmaj7", [60, 64, 67, 71]),   # C4  E4  G4  B4
    ("G",     [55, 59, 62, 69]),   # G3  B3  D4  A4
]
BASS_ROOTS = [33, 29, 36, 31]      # A1  F1  C2  G1

# General MIDI percussion keys.
KICK, CLAP, HAT_CLOSED, HAT_OPEN = 36, 39, 42, 46


def varlen(value):
    """Encode an int as a MIDI variable-length quantity."""
    if value < 0:
        raise ValueError("negative delta time")
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(out)


def build_track(notes, channel=0):
    """notes: iterable of (start_beat, length_beats, pitch, velocity)."""
    events = []
    for start, length, pitch, velocity in notes:
        on = int(round(start * PPQ))
        off = on + max(1, int(round(length * PPQ)))
        # Sort key keeps note-offs ahead of note-ons at the same tick, so a
        # repeated pitch retriggers instead of being cut short by its own tail.
        events.append((on, 1, 0x90 | channel, pitch, velocity))
        events.append((off, 0, 0x80 | channel, pitch, 0))
    events.sort(key=lambda e: (e[0], e[1]))

    data = bytearray()
    tempo = 60_000_000 // BPM
    data += b"\x00\xff\x51\x03" + struct.pack(">I", tempo)[1:]
    data += b"\x00\xff\x58\x04\x04\x02\x18\x08"          # 4/4

    prev = 0
    for tick, _, status, pitch, velocity in events:
        data += varlen(tick - prev) + bytes([status, pitch, velocity])
        prev = tick

    data += b"\x00\xff\x2f\x00"                           # end of track
    return bytes(data)


def write_midi(name, notes, channel=0):
    track = build_track(notes, channel)
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ)
    body = b"MTrk" + struct.pack(">I", len(track)) + track
    path = os.path.join(OUT_DIR, name)
    with open(path, "wb") as fh:
        fh.write(header + body)
    print(f"  {name}  ({len(notes)} notes, {os.path.getsize(path)} bytes)")


def chords():
    notes = []
    for bar in range(BARS):
        _, pitches = PROGRESSION[bar % len(PROGRESSION)]
        start = bar * BEATS_PER_BAR
        for i, pitch in enumerate(pitches):
            # A few ticks of spread per voice: a block chord landing perfectly
            # flat is the single most synthetic-sounding thing in a mix.
            notes.append((start + i * 0.01, BEATS_PER_BAR - 0.15, pitch, 78 + i * 3))
    return notes


def bass():
    notes = []
    for bar in range(BARS):
        root = BASS_ROOTS[bar % len(BASS_ROOTS)]
        start = bar * BEATS_PER_BAR
        for beat in range(BEATS_PER_BAR):
            # Offbeat eighths only — beat 1 is left to the kick.
            notes.append((start + beat + 0.5, 0.42, root, 100))
            if beat == 3:
                notes.append((start + beat + 0.75, 0.2, root + 12, 88))
    return notes


def arp():
    notes = []
    step = 0.25                                            # sixteenths
    for bar in range(BARS):
        _, pitches = PROGRESSION[bar % len(PROGRESSION)]
        shape = pitches + [p + 12 for p in pitches]        # two octaves up
        start = bar * BEATS_PER_BAR
        for i in range(BEATS_PER_BAR * 4):
            pitch = shape[i % len(shape)]
            velocity = 96 if i % 4 == 0 else 72            # accent the downbeats
            notes.append((start + i * step, step * 0.9, pitch, velocity))
    return notes


def drums():
    notes = []
    for bar in range(BARS):
        start = bar * BEATS_PER_BAR
        for beat in range(BEATS_PER_BAR):
            notes.append((start + beat, 0.25, KICK, 110))
            if beat in (1, 3):
                notes.append((start + beat, 0.25, CLAP, 100))
            # Open hat on the offbeat is what gives house its lift.
            hat = HAT_OPEN if beat % 2 == 1 else HAT_CLOSED
            notes.append((start + beat + 0.5, 0.2, hat, 84))
    return notes


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Writing {BARS}-bar loops at {BPM} BPM in A minor to {OUT_DIR}/")
    write_midi("chords_Am_130.mid", chords())
    write_midi("bass_Am_130.mid", bass())
    write_midi("arp_Am_130.mid", arp())
    write_midi("drums_130.mid", drums(), channel=9)   # channel 10 = percussion


if __name__ == "__main__":
    main()
