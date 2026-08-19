#!/usr/bin/env python3
"""Analyse a vocal stem and produce the section map the remix spec asks for.

Implements the ANALYZE and MAP stages: tempo, key, where the singing actually
happens, and — the part that matters — which blocks repeat, so the chorus is
identified by recurrence rather than by loudness alone.

    python3 analyze_vocal.py "vocal.wav"
    python3 analyze_vocal.py "vocal.wav" --bpm 128 --gap 2.0

Writes next to the audio file:
    <name>.map.json      the section map, machine-readable
    <name>.markers.lua   a ReaScript that drops the sections into REAPER as regions

The labelling is a first pass and says so: every section carries a confidence
score. Open the markers in REAPER, listen once, drag what is wrong. That is
faster than mapping the whole song by hand, which is the entire point.

UNVALIDATED: this script has never been executed, on real audio or synthetic.
It is committed so the work is not lost, not because it is known to work.
Expect to debug it on first run. Requires: librosa, soundfile, numpy.
"""

import argparse
import json
import os
import sys

import librosa
import numpy as np

# Krumhansl-Schmuckler key profiles.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]

SR = 22050
HOP = 512


def detect_key(y):
    """Correlate the average chroma against both key profiles; best wins."""
    chroma = librosa.feature.chroma_cens(y=y, sr=SR, hop_length=HOP)
    avg = chroma.mean(axis=1)
    if avg.sum() == 0:
        return {"key": "unknown", "camelot": None, "confidence": 0.0}

    best = (-2.0, 0, "major")
    for pc in range(12):
        rotated = np.roll(avg, -pc)
        for name, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            score = float(np.corrcoef(rotated, profile)[0, 1])
            if score > best[0]:
                best = (score, pc, name)

    score, pc, mode = best
    camelot = CAMELOT_MAJOR[pc] if mode == "major" else CAMELOT_MINOR[pc]
    return {
        "key": f"{NOTES[pc]} {mode}",
        "camelot": camelot,
        "confidence": round(max(0.0, score), 3),
    }


def find_phrases(y, min_len=0.25, join_gap=0.35):
    """Where is there actually singing? Returns (start, end) pairs in seconds.

    A vocal stem is mostly silence between lines, which makes an energy gate a
    far more reliable phrase detector here than it would be on a full mix.
    """
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=SR, hop_length=HOP)

    # Gate relative to the track's own noise floor rather than a fixed dB value,
    # so a quietly-bounced stem is treated the same as a hot one.
    floor = np.percentile(rms, 10)
    ceiling = np.percentile(rms, 95)
    if ceiling <= floor:
        return []
    threshold = floor + (ceiling - floor) * 0.08

    voiced = rms > threshold
    phrases = []
    start = None
    for i, on in enumerate(voiced):
        if on and start is None:
            start = times[i]
        elif not on and start is not None:
            phrases.append([start, times[i]])
            start = None
    if start is not None:
        phrases.append([start, times[-1]])

    merged = []
    for ph in phrases:
        if merged and ph[0] - merged[-1][1] <= join_gap:
            merged[-1][1] = ph[1]
        else:
            merged.append(ph)
    return [tuple(p) for p in merged if p[1] - p[0] >= min_len]


def group_blocks(phrases, gap):
    """A silence longer than `gap` means a new section started."""
    blocks = []
    for start, end in phrases:
        if blocks and start - blocks[-1]["end"] < gap:
            blocks[-1]["end"] = end
            blocks[-1]["phrases"] += 1
        else:
            blocks.append({"start": start, "end": end, "phrases": 1})
    return blocks


def block_signature(y, block, length=32):
    """A fixed-length chroma contour, so blocks of different lengths compare."""
    a = int(block["start"] * SR)
    b = int(block["end"] * SR)
    seg = y[a:b]
    if len(seg) < HOP * 4:
        return None
    chroma = librosa.feature.chroma_cens(y=seg, sr=SR, hop_length=HOP)
    idx = np.linspace(0, chroma.shape[1] - 1, length).astype(int)
    sig = chroma[:, idx].flatten()
    norm = np.linalg.norm(sig)
    return sig / norm if norm > 0 else None


def cluster(signatures, threshold):
    """Greedy grouping: each block joins the first group it strongly matches."""
    groups = []
    labels = [-1] * len(signatures)
    for i, sig in enumerate(signatures):
        if sig is None:
            continue
        for g, members in enumerate(groups):
            ref = signatures[members[0]]
            if ref is not None and float(np.dot(sig, ref)) >= threshold:
                members.append(i)
                labels[i] = g
                break
        else:
            groups.append([i])
            labels[i] = len(groups) - 1
    return groups, labels


def label_sections(blocks, groups, labels, energies, total):
    """Turn clusters into musical names.

    The chorus is the group that both recurs and carries the most energy —
    recurrence alone would tie with the verse, energy alone would misfire on a
    belted bridge. Requiring both is what the spec asks for.
    """
    recurring = [g for g, m in enumerate(groups) if len(m) >= 2]

    chorus_group = None
    if recurring:
        chorus_group = max(
            recurring,
            key=lambda g: (np.mean([energies[i] for i in groups[g]]), len(groups[g])),
        )

    verse_groups = [g for g in recurring if g != chorus_group]

    sections = []
    for i, block in enumerate(blocks):
        g = labels[i]
        confidence = 0.5
        if g == chorus_group:
            name, confidence = "Chorus", 0.8
        elif g in verse_groups:
            name, confidence = "Verse", 0.7
        elif block["start"] > total * 0.55:
            # A one-off block late in the song is almost always the bridge.
            name, confidence = "Bridge", 0.5
        else:
            name, confidence = "Section", 0.35
        sections.append({**block, "name": name, "group": g, "confidence": confidence})

    # A non-recurring block sitting directly before a chorus is a pre-chorus.
    for i in range(len(sections) - 1):
        if sections[i + 1]["name"] == "Chorus" and sections[i]["name"] in ("Section", "Bridge"):
            sections[i]["name"] = "Pre-Chorus"
            sections[i]["confidence"] = 0.55

    # Number the repeats so the map reads like an arrangement.
    counts = {}
    for s in sections:
        counts[s["name"]] = counts.get(s["name"], 0) + 1
        s["label"] = f"{s['name']} {counts[s['name']]}"
    return sections


def snap_to_bars(sections, bpm, first_beat):
    """Nudge every boundary onto the nearest bar line, in place."""
    bar = 4 * 60.0 / bpm
    for s in sections:
        s["start_snapped"] = round(first_beat + round((s["start"] - first_beat) / bar) * bar, 3)
        s["end_snapped"] = round(first_beat + round((s["end"] - first_beat) / bar) * bar, 3)
        if s["end_snapped"] <= s["start_snapped"]:
            s["end_snapped"] = round(s["start_snapped"] + bar, 3)
        s["bars"] = int(round((s["end_snapped"] - s["start_snapped"]) / bar))
    return sections


def write_lua(path, sections, meta):
    """A ReaScript is more reliable than guessing REAPER's marker CSV dialect."""
    rows = ",\n".join(
        '  {{name = "{0}", pos = {1}, stop = {2}}}'.format(
            s["label"].replace('"', "'"), s["start_snapped"], s["end_snapped"]
        )
        for s in sections
    )
    lua = f"""-- Section map generated by analyze_vocal.py
-- {meta['file']}  |  {meta['bpm']} BPM  |  {meta['key']['key']} ({meta['key']['camelot']})
-- Run in REAPER: Actions > Show action list > Load ReaScript > select this file > Run.
-- Boundaries are snapped to bars but are a first pass -- drag any that are wrong.

local sections = {{
{rows}
}}

reaper.Undo_BeginBlock()
for _, s in ipairs(sections) do
  reaper.AddProjectMarker2(0, true, s.pos, s.stop, s.name, -1, 0)
end
reaper.Undo_EndBlock("Import vocal section map", -1)
reaper.UpdateArrange()
reaper.ShowConsoleMsg("Added " .. #sections .. " regions from the vocal analysis\\n")
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(lua)


def main():
    ap = argparse.ArgumentParser(description="Map a vocal stem into sections.")
    ap.add_argument("audio", help="path to the vocal file (wav/mp3/flac/m4a)")
    ap.add_argument("--bpm", type=float, help="override the detected tempo")
    ap.add_argument("--gap", type=float, default=1.8,
                    help="silence in seconds that separates sections (default 1.8)")
    ap.add_argument("--similarity", type=float, default=0.82,
                    help="how alike two blocks must be to count as the same section")
    args = ap.parse_args()

    if not os.path.exists(args.audio):
        sys.exit(f"No such file: {args.audio}")

    y, _ = librosa.load(args.audio, sr=SR, mono=True)
    total = len(y) / SR
    if total < 5:
        sys.exit("That file is under 5 seconds — nothing to map.")

    tempo, beats = librosa.beat.beat_track(y=y, sr=SR, hop_length=HOP)
    detected = float(np.atleast_1d(tempo)[0])
    bpm = args.bpm or round(detected, 2)
    beat_times = librosa.frames_to_time(beats, sr=SR, hop_length=HOP)
    first_beat = float(beat_times[0]) if len(beat_times) else 0.0

    key = detect_key(y)

    phrases = find_phrases(y)
    if not phrases:
        sys.exit("No singing detected — is this actually a vocal stem?")

    blocks = group_blocks(phrases, args.gap)
    signatures = [block_signature(y, b) for b in blocks]
    energies = [
        float(np.sqrt(np.mean(y[int(b["start"] * SR):int(b["end"] * SR)] ** 2)) or 0.0)
        for b in blocks
    ]
    groups, labels = cluster(signatures, args.similarity)
    sections = label_sections(blocks, groups, labels, energies, total)
    sections = snap_to_bars(sections, bpm, first_beat)

    meta = {
        "file": os.path.basename(args.audio),
        "duration_sec": round(total, 2),
        "bpm": bpm,
        "bpm_detected": round(detected, 2),
        "bpm_overridden": args.bpm is not None,
        "key": key,
        "bar_seconds": round(4 * 60.0 / bpm, 4),
        "phrases": len(phrases),
        "sections": [
            {
                "label": s["label"],
                "type": s["name"],
                "start": s["start_snapped"],
                "end": s["end_snapped"],
                "bars": s["bars"],
                "phrases": s["phrases"],
                "repeat_group": s["group"],
                "confidence": s["confidence"],
            }
            for s in sections
        ],
    }

    base = os.path.splitext(args.audio)[0]
    with open(base + ".map.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    write_lua(base + ".markers.lua", sections, meta)

    print(f"\n{meta['file']}  {meta['duration_sec']}s")
    print(f"  BPM {bpm}" + ("" if args.bpm else f" (detected)"))
    print(f"  Key {key['key']}  Camelot {key['camelot']}  (confidence {key['confidence']})")
    print(f"  {len(phrases)} vocal phrases in {len(sections)} sections\n")
    print(f"  {'start':>8}  {'bars':>4}  {'conf':>4}  section")
    for s in meta["sections"]:
        m, sec = divmod(s["start"], 60)
        print(f"  {int(m):>5}:{sec:05.2f}  {s['bars']:>4}  {s['confidence']:>4.2f}  {s['label']}")
    print(f"\nWrote {os.path.basename(base)}.map.json and {os.path.basename(base)}.markers.lua")
    print("Load the .lua in REAPER to drop these in as regions, then fix by ear.")


if __name__ == "__main__":
    main()
