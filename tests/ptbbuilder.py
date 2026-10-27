# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Willie Wrinkle <williewrinkle@gmail.com>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details: <https://www.gnu.org/licenses/>.

"""Builds Power Tab 1.7 files for tests.

`to_bytes()` writes the parser's own data classes back out in the .ptb
layout, and the small factory functions below make songs quick to describe:

    doc = song(score([system([staff([pos(0, 4, notes=[note(5, 0)])])])]))
    data = to_bytes(doc)
"""

import struct
from typing import Iterable, List, Optional, Sequence

from ptb2ly import ptbparser as P

# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class Writer:
    def __init__(self):
        self.out = bytearray()
        self.classes = {}
        self.map_count = 1        # MFC numbering, as the parser tracks it

    def u8(self, v):
        self.out += struct.pack("<B", v)

    def i8(self, v):
        self.out += struct.pack("<b", v)

    def u16(self, v):
        self.out += struct.pack("<H", v)

    def u32(self, v):
        self.out += struct.pack("<I", v)

    def i32(self, v):
        self.out += struct.pack("<i", v)

    def count(self, n):
        if n < 0xFFFF:
            self.u16(n)
        else:
            self.u16(0xFFFF)
            self.u32(n)

    def string(self, s: str):
        data = s.encode("cp1252")
        n = len(data)
        if n < 0xFF:
            self.u8(n)
        elif n < 0xFFFF:
            self.u8(0xFF)
            self.u16(n)
        else:
            self.u8(0xFF)
            self.u16(0xFFFF)
            self.u32(n)
        self.out += data

    def class_tag(self, name: str):
        if name in self.classes:
            self.u16(0x8000 | self.classes[name])
        else:
            self.u16(0xFFFF)
            self.u16(1)
            self.u16(len(name))
            self.out += name.encode("ascii")
            self.classes[name] = self.map_count
            self.map_count += 1
        self.map_count += 1

    def vector(self, name: str, items, write_item):
        self.count(len(items))
        for item in items:
            self.class_tag(name)
            write_item(item)

    def small_u8(self, values):
        self.u8(len(values))
        for v in values:
            self.u8(v)

    def small_u16(self, values):
        self.u8(len(values))
        for v in values:
            self.u16(v)

    def small_u32(self, values):
        self.u8(len(values))
        for v in values:
            self.u32(v)


def write_header(w: Writer, h: P.Header):
    w.out += P.MARKER
    w.u16(h.version)
    w.u8(h.file_type)
    if h.file_type == P.FILETYPE_SONG:
        w.u8(h.content_type)
        w.string(h.title)
        w.string(h.artist)
        w.u8(h.release_type)
        if h.release_type == 0:
            w.u8(h.audio_type)
            w.string(h.release_title)
            w.u16(h.year)
            w.u8(int(h.live))
        elif h.release_type == 1:
            w.string(h.release_title)
            w.u8(int(h.live))
        elif h.release_type == 2:
            w.string(h.release_title)
            w.u16(1)
            w.u16(1)
            w.u16(h.year)
        w.u8(h.author_type)
        if h.author_type == 0:
            w.string(h.composer)
            w.string(h.lyricist)
        for text in (h.arranger, h.guitar_transcriber, h.bass_transcriber, h.copyright,
                     h.lyrics, h.guitar_notes, h.bass_notes):
            w.string(text)
    else:
        w.string(h.title)
        w.string(h.subtitle)
        w.u16(h.music_style)
        w.u8(h.level)
        w.string(h.author)
        w.string(h.notes)
        w.string(h.copyright)


def write_chord_name(w: Writer, c: P.ChordName):
    w.u16(c.key)
    w.u8(c.formula)
    w.u16(c.modifications)
    w.u8(c.extra)


def write_font(w: Writer):
    w.string("Arial")
    w.i32(10)
    w.i32(400)
    w.u8(0)
    w.u8(0)
    w.u8(0)
    w.u32(0)


def write_barline(w: Writer, b: P.Barline):
    w.u8(b.position)
    w.u8(b.data)
    w.u8(b.key.data)
    w.u32(b.time.data)
    w.u8(b.time.pulses)
    w.i8(b.rehearsal.letter)
    w.string(b.rehearsal.description)


def write_note(w: Writer, n: P.Note):
    w.u8(n.string_data)
    w.u16(n.simple)
    w.small_u32(n.complex)


def write_position(w: Writer, p: P.Position):
    w.u8(p.position)
    w.u16(p.beaming)
    w.u32(p.data)
    w.small_u32(p.complex)
    w.vector("CLineData", p.notes, lambda n: write_note(w, n))


def write_staff(w: Writer, st: P.Staff):
    w.u8(st.data)
    for _ in range(4):
        w.u8(0)
    for voice in st.voices:
        w.vector("CPosition", voice, lambda p: write_position(w, p))


def write_system(w: Writer, s: P.System):
    for v in s.rect:
        w.i32(v)
    w.u8(s.end_bar_data)
    w.u8(s.position_spacing)
    for _ in range(3):
        w.u8(0)
    write_barline(w, s.start_bar)

    def direction(d):
        w.u8(d.position)
        w.small_u16(d.symbols)

    def chord_text(c):
        w.u8(c.position)
        write_chord_name(w, c.name)

    def slash(r):
        w.u8(r.position)
        w.u8(r.beaming)
        w.u32(r.data)

    w.vector("CDirection", s.directions, direction)
    w.vector("CChordText", s.chord_texts, chord_text)
    w.vector("CRhythmSlash", s.rhythm_slashes, slash)
    w.vector("CStaff", s.staves, lambda st: write_staff(w, st))
    w.vector("CMusicBar", s.barlines, lambda b: write_barline(w, b))


def write_score(w: Writer, sc: P.Score):
    def guitar(g):
        w.u8(g.number)
        w.string(g.description)
        for v in (g.preset, g.volume, g.pan, g.reverb, g.chorus, g.tremolo, g.phaser, g.capo):
            w.u8(v)
        w.string(g.tuning.name)
        w.u8(g.tuning.data)
        w.small_u8(g.tuning.notes)

    def diagram(d):
        write_chord_name(w, d.name)
        w.u8(d.top_fret)
        w.small_u8(d.frets)

    def floating(f):
        w.string(f.text)
        for v in f.rect:
            w.i32(v)
        w.u8(f.flags)
        write_font(w)

    def guitar_in(g):
        w.u16(g.system)
        w.u8(g.staff)
        w.u8(g.position)
        w.u16(g.data)

    def tempo(t):
        w.u16(t.system)
        w.u8(t.position)
        w.u32(t.data)
        w.string(t.description)

    def dynamic(d):
        w.u16(d.system)
        w.u8(d.staff)
        w.u8(d.position)
        w.u16(d.data)

    def ending(e):
        w.u16(e.system)
        w.u8(e.position)
        w.u32(e.data)

    w.vector("CGuitar", sc.guitars, guitar)
    w.vector("CChordDiagram", sc.chord_diagrams, diagram)
    w.vector("CFloatingText", sc.floating_texts, floating)
    w.vector("CGuitarIn", sc.guitar_ins, guitar_in)
    w.vector("CTempoMarker", sc.tempo_markers, tempo)
    w.vector("CDynamic", sc.dynamics, dynamic)
    w.vector("CAlternateEnding", sc.alternate_endings, ending)
    w.vector("CSection", sc.systems, lambda s: write_system(w, s))


def to_bytes(doc: P.Document) -> bytes:
    w = Writer()
    write_header(w, doc.header)
    write_score(w, doc.guitar_score)
    write_score(w, doc.bass_score)
    for _ in range(3):
        write_font(w)
    w.i32(9)
    w.u32(0)
    w.u32(0)
    return bytes(w.out)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

STANDARD = [64, 59, 55, 50, 45, 40]
BASS = [43, 38, 33, 28]


def note(string: int, fret: int, flags: int = 0, complex: Iterable[int] = ()) -> P.Note:
    return P.Note((string << 5) | fret, flags, list(complex))


def pos(index: int, duration: int = 4, flags: int = 0, notes: Sequence[P.Note] = (),
        beaming: int = 0, complex: Iterable[int] = ()) -> P.Position:
    if not notes:
        flags |= P.REST
    return P.Position(index, beaming, (duration << 24) | flags, list(complex), list(notes))


def rest(index: int, duration: int = 4, flags: int = 0) -> P.Position:
    return pos(index, duration, flags)


def time_data(beats: int = 4, value: int = 4, shown: bool = True, flags: int = 0) -> int:
    return ((beats - 1) << 27) | ((value.bit_length() - 1) << 24) | (0x100000 if shown else 0) | flags


def barline(position: int = 0, type: int = 0, repeat: int = 0, fifths: int = 0,
            minor: bool = False, key_shown: bool = True, cancellation: bool = False,
            beats: int = 4, value: int = 4, time_shown: bool = True, time_flags: int = 0,
            letter: Optional[str] = None, text: str = "") -> P.Barline:
    acc = fifths if fifths >= 0 else 7 - fifths
    key = acc | (0x40 if minor else 0) | (0x10 if key_shown else 0) | (0x20 if cancellation else 0)
    return P.Barline(position, (type << 5) | repeat, P.KeySignature(key),
                     P.TimeSignature(time_data(beats, value, time_shown, time_flags), beats),
                     P.RehearsalSign(ord(letter) if letter else 0x7F, text))


def staff(voice1: Sequence[P.Position] = (), voice2: Sequence[P.Position] = (),
          strings: int = 6, clef: int = 0) -> P.Staff:
    return P.Staff((clef << 4) | strings, [list(voice1), list(voice2)])


def system(staves: Sequence[P.Staff], barlines: Sequence[P.Barline] = (),
           start: Optional[P.Barline] = None, end_type: int = 0, end_repeat: int = 0,
           directions: Sequence[P.Direction] = (), chords: Sequence[P.ChordText] = (),
           slashes: Sequence[P.RhythmSlash] = (), rect=(0, 0, 800, 100),
           spacing: int = 20) -> P.System:
    return P.System(tuple(rect), (end_type << 5) | end_repeat, spacing, start or barline(),
                    list(directions), list(chords), list(slashes), list(staves), list(barlines))


def tuning(notes: Sequence[int] = STANDARD, name: str = "Standard", sharps: bool = True,
           offset: int = 0) -> P.Tuning:
    data = (1 if sharps else 0) | ((abs(offset) & 0x3F) << 1) | (0x80 if offset < 0 else 0)
    return P.Tuning(name, data, list(notes))


def guitar(number: int = 0, notes: Sequence[int] = STANDARD, capo: int = 0,
           description: str = "Acoustic", preset: int = 25, volume: int = 104, pan: int = 64,
           reverb: int = 0, chorus: int = 0, tuning_name: str = "Standard",
           sharps: bool = True, offset: int = 0) -> P.Guitar:
    return P.Guitar(number, description, preset, volume, pan, reverb, chorus, 0, 0, capo,
                    tuning(notes, tuning_name, sharps, offset))


def guitar_in(system: int, staff: int, position: int, guitars: Sequence[int] = (0,),
              slash_guitars: Sequence[int] = ()) -> P.GuitarIn:
    staff_bits = sum(1 << g for g in guitars)
    slash_bits = sum(1 << g for g in slash_guitars)
    return P.GuitarIn(system, staff, position, (staff_bits << 8) | slash_bits)


def tempo(system: int = 0, position: int = 0, bpm: int = 120, type: int = 1,
          beat: int = 2, listesso: int = 0, triplet_feel: int = 0,
          description: str = "") -> P.TempoMarker:
    data = (type << 27) | (beat << 23) | (listesso << 19) | (triplet_feel << 16) | bpm
    return P.TempoMarker(system, position, data, description)


def dynamic(system: int, staff: int, position: int, staff_volume: int = 0xFF,
            slash_volume: int = 0xFF) -> P.Dynamic:
    return P.Dynamic(system, staff, position, (staff_volume << 8) | slash_volume)


def ending(system: int, position: int, numbers: Sequence[int] = (1,),
           da_capo: bool = False, dal_segno: bool = False,
           dal_segno_segno: bool = False) -> P.AlternateEnding:
    bits = sum(1 << (n - 1) for n in numbers)
    bits |= (1 << 8 if da_capo else 0) | (1 << 9 if dal_segno else 0) | (1 << 10 if dal_segno_segno else 0)
    return P.AlternateEnding(system, position, bits << 16)


def direction(position: int, *symbols) -> P.Direction:
    """symbols: (type, active, repeat) tuples."""
    return P.Direction(position, [(t << 8) | (a << 6) | r for t, a, r in symbols])


def chord_name(tonic: int = 4, formula: int = 0, bass: Optional[int] = None,
               modifications: int = 0, extra: int = 0, tonic_variation: int = 1,
               bass_variation: int = 1, flags: int = 0) -> P.ChordName:
    bass = tonic if bass is None else bass
    key = (tonic << 8) | (tonic_variation << 12) | bass | (bass_variation << 4)
    return P.ChordName(key, formula | flags, modifications, extra)


def chord_text(position: int, name: P.ChordName) -> P.ChordText:
    return P.ChordText(position, name)


def slash(index: int, duration: int = 4, flags: int = 0, beaming: int = 0,
          single: Optional[tuple] = None) -> P.RhythmSlash:
    data = ((duration.bit_length() - 1) << 21) | flags
    if single:
        string, fret = single
        data |= P.SLASH_SINGLE_NOTE | (string << 24) | (fret << 27)
    return P.RhythmSlash(index, beaming, data)


def diagram(name: P.ChordName, frets: Sequence[int], top: int = 0) -> P.ChordDiagram:
    return P.ChordDiagram(name, top, list(frets))


def floating(text: str, rect=(100, 10, 200, 30)) -> P.FloatingText:
    return P.FloatingText(text, tuple(rect), 0)


def score(systems: Sequence[P.System] = (), guitars: Optional[List[P.Guitar]] = None,
          guitar_ins: Optional[List[P.GuitarIn]] = None, tempos: Sequence[P.TempoMarker] = (),
          dynamics: Sequence[P.Dynamic] = (), endings: Sequence[P.AlternateEnding] = (),
          diagrams: Sequence[P.ChordDiagram] = (),
          floating_texts: Sequence[P.FloatingText] = ()) -> P.Score:
    if guitars is None:
        guitars = [guitar()] if systems else []
    if guitar_ins is None:
        guitar_ins = [guitar_in(0, 0, 0)] if systems else []
    return P.Score(list(guitars), list(diagrams), list(floating_texts), list(guitar_ins),
                   list(tempos), list(dynamics), list(endings), list(systems))


def song(guitar_score: Optional[P.Score] = None, bass_score: Optional[P.Score] = None,
         **header) -> P.Document:
    h = P.Header(version=4, file_type=P.FILETYPE_SONG, content_type=1,
                 title="Test Song", artist="Test Artist", release_type=3)
    for k, v in header.items():
        setattr(h, k, v)
    return P.Document(h, guitar_score or score(), bass_score or score())


def one_bar(*positions: P.Position, **system_args) -> P.Document:
    """A song with one staff holding the given positions."""
    return song(score([system([staff(positions)], **system_args)]))
