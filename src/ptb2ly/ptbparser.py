# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Willie Wrinkle <williewrinkle@gmail.com>
#
# Ported from the PowerTabDocument classes in Power Tab Editor 2.0
# (https://github.com/powertab/powertabeditor), Copyright (C) Cameron White
# and the Power Tab Editor contributors, GPL-3.0-or-later. Those classes are
# based on Brad Larsen's original Power Tab Editor 1.7 source,
# Copyright (C) Brad Larsen.
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

"""Parser for Power Tab Editor 1.x (.ptb) files.

A Python port of the PowerTabDocument classes from Power Tab Editor 2.0
(source/formats/powertab_old/powertabdocument/), which in turn come from
Brad Larsen's original Power Tab 1.7 source.

The file is an MFC CArchive: little-endian integers, MFC strings, and
object arrays where each element is preceded by MFC class information.

Only the v1.7 layout (file version 4) is supported for the body; all files
in the library use it.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Callable, List, Optional, TypeVar

T = TypeVar("T")

MARKER = b"ptab"
MAX_COUNT = 100_000              # far more items than any real file has
VERSION_1_7 = 4

FILETYPE_SONG = 0
FILETYPE_LESSON = 1


class PtbError(Exception):
    """Raised when a file can't be parsed."""


# ---------------------------------------------------------------------------
# Binary stream
# ---------------------------------------------------------------------------

class Stream:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        # MFC numbers every class and object in the order it appears; a
        # class tag refers back to a class by that number.
        self.map_count = 1
        self.class_indices = set()

    def _unpack(self, fmt: str, size: int):
        if self.pos + size > len(self.data):
            raise PtbError(f"unexpected end of file at offset {self.pos}")
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += size
        return value

    def u8(self) -> int:
        return self._unpack("<B", 1)

    def i8(self) -> int:
        return self._unpack("<b", 1)

    def u16(self) -> int:
        return self._unpack("<H", 2)

    def u32(self) -> int:
        return self._unpack("<I", 4)

    def i32(self) -> int:
        return self._unpack("<i", 4)

    def skip(self, n: int) -> None:
        self.pos += n

    def count(self) -> int:
        """MFC count: 16-bit, or 0xffff followed by 32-bit."""
        n = self.u16()
        if n == 0xFFFF:
            n = self.u32()
        if n > MAX_COUNT:
            raise PtbError(f"implausible item count {n} at offset {self.pos}")
        return n

    def string(self) -> str:
        """MFC CString (Windows-1252 text)."""
        n = self.u8()
        if n == 0xFF:
            n = self.u16()
            if n == 0xFFFF:
                n = self.u32()
        if self.pos + n > len(self.data):
            raise PtbError(f"string runs past end of file at offset {self.pos}")
        raw = self.data[self.pos:self.pos + n]
        try:
            s = raw.decode("cp1252")   # Windows ANSI code page
        except UnicodeDecodeError:
            s = raw.decode("latin-1")
        self.pos += n
        return s

    def rect(self):
        return tuple(self.i32() for _ in range(4))

    def color(self) -> int:
        return self.u32()

    def class_info(self) -> None:
        """Skip the MFC class tag that precedes each object in an array."""
        word_tag = self.u16()
        if word_tag == 0x7FFF:
            obj_tag = self.u32()
        else:
            obj_tag = ((word_tag & 0x8000) << 16) | (word_tag & ~0x8000 & 0xFFFF)
        if not (obj_tag & 0x80000000):
            # An object reference: never used by Power Tab files, so this
            # means the data is misaligned.
            raise PtbError(f"unexpected object tag {word_tag:#06x} at offset {self.pos - 2}")
        if word_tag == 0xFFFF:  # new class: schema + class name follow
            self.u16()  # schema
            length = self.u16()
            name = self.data[self.pos:self.pos + length]
            if not (0 < length <= 64 and name[:1] == b"C" and name.isalnum()):
                raise PtbError(f"bad class name at offset {self.pos}")
            self.skip(length)
            self.class_indices.add(self.map_count)
            self.map_count += 1
        elif (obj_tag & 0x7FFFFFFF) not in self.class_indices:
            raise PtbError(f"unknown class number {obj_tag & 0x7FFFFFFF} at offset {self.pos}")
        self.map_count += 1      # the object itself

    def vector(self, read: Callable[["Stream"], T]) -> List[T]:
        n = self.count()
        out = []
        for _ in range(n):
            self.class_info()
            out.append(read(self))
        return out

    def small_vector_u8(self) -> List[int]:
        n = self.u8()
        return [self.u8() for _ in range(n)]

    def small_vector_u16(self) -> List[int]:
        n = self.u8()
        return [self.u16() for _ in range(n)]

    def small_vector_u32(self) -> List[int]:
        n = self.u8()
        return [self.u32() for _ in range(n)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_complex(symbols: List[int], type_char: str) -> Optional[int]:
    """Complex symbols store their type as an ASCII letter in the top byte."""
    t = ord(type_char)
    for s in symbols:
        if (s >> 24) & 0xFF == t:
            return s
    return None


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

@dataclass
class Header:
    version: int = 0
    file_type: int = FILETYPE_SONG
    content_type: int = 0
    title: str = ""
    artist: str = ""
    release_type: int = 0
    release_title: str = ""
    audio_type: int = 0           # 0 single, 1 EP, 2 album, 3 double, 4 triple, 5 box set
    year: int = 0
    live: bool = False
    author_type: int = 0          # 0 = known, 1 = traditional
    composer: str = ""
    lyricist: str = ""
    arranger: str = ""
    guitar_transcriber: str = ""
    bass_transcriber: str = ""
    copyright: str = ""
    lyrics: str = ""
    guitar_notes: str = ""
    bass_notes: str = ""
    # lesson-only
    subtitle: str = ""
    music_style: int = 0
    level: int = 0
    author: str = ""
    notes: str = ""


def read_header(s: Stream) -> Header:
    if s.data[:4] != MARKER:
        raise PtbError("not a Power Tab file (missing 'ptab' marker)")
    s.skip(4)
    h = Header()
    h.version = s.u16()
    if h.version != VERSION_1_7:
        raise PtbError(f"unsupported file version {h.version} (only v1.7 supported)")
    h.file_type = s.u8()
    if h.file_type == FILETYPE_SONG:
        h.content_type = s.u8()
        h.title = s.string()
        h.artist = s.string()
        h.release_type = s.u8()
        if h.release_type == 0:          # public audio
            h.audio_type = s.u8()
            h.release_title = s.string()
            h.year = s.u16()
            h.live = bool(s.u8())
        elif h.release_type == 1:        # public video
            h.release_title = s.string()
            h.live = bool(s.u8())
        elif h.release_type == 2:        # bootleg
            h.release_title = s.string()
            s.u16()                      # month
            s.u16()                      # day
            h.year = s.u16()
        h.author_type = s.u8()
        if h.author_type == 0:
            h.composer = s.string()
            h.lyricist = s.string()
        h.arranger = s.string()
        h.guitar_transcriber = s.string()
        h.bass_transcriber = s.string()
        h.copyright = s.string()
        h.lyrics = s.string()
        h.guitar_notes = s.string()
        h.bass_notes = s.string()
    elif h.file_type == FILETYPE_LESSON:
        h.title = s.string()
        h.subtitle = s.string()
        h.music_style = s.u16()
        h.level = s.u8()
        h.author = s.string()
        h.notes = s.string()
        h.copyright = s.string()
    else:
        raise PtbError(f"invalid file type {h.file_type}")
    return h


# ---------------------------------------------------------------------------
# Score objects
# ---------------------------------------------------------------------------

@dataclass
class Tuning:
    name: str
    data: int
    notes: List[int]              # MIDI notes, high string first

    @property
    def notation_offset(self) -> int:
        v = (self.data & 0x7E) >> 1
        return -v if self.data & 0x80 else v

    @property
    def sharps(self) -> bool:
        return bool(self.data & 0x01)


def read_tuning(s: Stream) -> Tuning:
    name = s.string()
    data = s.u8()
    notes = s.small_vector_u8()
    return Tuning(name, data, notes)


@dataclass
class Guitar:
    number: int
    description: str
    preset: int
    volume: int
    pan: int
    reverb: int
    chorus: int
    tremolo: int
    phaser: int
    capo: int
    tuning: Tuning


def read_guitar(s: Stream) -> Guitar:
    number = s.u8()
    desc = s.string()
    vals = [s.u8() for _ in range(8)]
    tuning = read_tuning(s)
    return Guitar(number, desc, *vals, tuning=tuning)


@dataclass
class ChordName:
    key: int
    formula: int
    modifications: int
    extra: int

    KEY_DEFAULT = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    KEY_DOWN = ["B#", "Bx", "Cx", "D#", "Dx", "E#", "Ex", "Fx", "G#", "Gx", "A#", "Ax"]
    KEY_UP = ["Dbb", "Db", "Ebb", "Fbb", "Fb", "Gbb", "Gb", "Abb", "", "Bbb", "Cbb", "Cb"]

    @staticmethod
    def _key_text(key: int, variation: int) -> str:
        key %= 12
        if variation == 1:
            return ChordName.KEY_DEFAULT[key]
        if variation == 0:
            return ChordName.KEY_DOWN[key]
        return ChordName.KEY_UP[key]

    @property
    def tonic(self):
        return (self.key & 0xF00) >> 8, (self.key & 0x3000) >> 12

    @property
    def bass(self):
        return self.key & 0xF, (self.key & 0x30) >> 4

    @property
    def no_chord(self) -> bool:
        return bool(self.formula & 0x10)

    @property
    def brackets(self) -> bool:
        return bool(self.formula & 0x20)

    @property
    def fret_position(self) -> Optional[int]:
        """Fret the chord is played at, or None."""
        v = self.extra & 0x1F
        return None if v == 0 or self.extra == 0xFF else v - 1

    @property
    def chord_type(self) -> Optional[int]:
        """Voicing type number (2-8), or None."""
        v = self.extra >> 5
        return None if v == 0 or self.extra == 0xFF else v + 1

    def formula_text(self) -> str:
        """Port of ChordName::GetFormulaText."""
        f = self.formula & 0x0F
        mods = self.modifications
        ab = ["maj", "m", "+", "°", "5", "add", "sus2", "sus4", "#", "b"]
        out = ""
        has_ext = False
        for bit, ext in ((0x01, "9"), (0x02, "11"), (0x04, "13")):
            if mods & bit:
                if f >= 8:
                    out += {8: ab[0], 9: ab[1], 10: ab[2], 11: ab[3],
                            12: ab[1] + "/" + ab[0]}.get(f, ab[1] + ext + "b5")
                    if f < 13:
                        out += ext
                elif f == 7:
                    out += ext
                has_ext = True
        suffixes = ["", ab[1], ab[2], ab[3], ab[4], "6", ab[1] + "6", "7",
                    ab[0] + "7", ab[1] + "7", ab[2] + "7", ab[3] + "7",
                    ab[1] + "/" + ab[0] + "7", "m7" + ab[9] + "5", "", ""]
        if not has_ext and f != 0:
            out += suffixes[f]
        additions = [
            (0x4000, ab[6]), (0x8000, ab[7]), (0x08, ab[5] + "2"),
            (0x10, ab[5] + "4"), (0x20, ab[5] + "6"), (0x40, ab[5] + "9"),
            (0x80, ab[5] + "11"), (0x2000, ab[9] + "13"), (0x1000, ab[2] + "11"),
            (0x400, ab[9] + "9"), (0x800, ab[2] + "9"), (0x100, ab[9] + "5"),
            (0x200, ab[2] + "5"),
        ]
        for bit, text in additions:
            if mods & bit:
                out += text
        return out

    def text(self) -> str:
        """Port of ChordName::GetText."""
        out = ""
        if self.no_chord:
            out = "N.C."
            if not self.brackets:
                return out
        if self.brackets:
            out += "("
        out += self._key_text(*self.tonic)
        out += self.formula_text()
        if self.bass != self.tonic:
            out += "/" + self._key_text(*self.bass)
        if self.brackets:
            out += ")"
        return out


def read_chord_name(s: Stream) -> ChordName:
    key = s.u16()
    formula = s.u8()
    mods = s.u16()
    extra = s.u8()
    return ChordName(key, formula, mods, extra)


@dataclass
class ChordDiagram:
    name: ChordName
    top_fret: int
    frets: List[int]


def read_chord_diagram(s: Stream) -> ChordDiagram:
    name = read_chord_name(s)
    top = s.u8()
    frets = s.small_vector_u8()
    return ChordDiagram(name, top, frets)


@dataclass
class FloatingText:
    text: str
    rect: tuple
    flags: int


def read_font_setting(s: Stream) -> None:
    s.string()   # face name
    s.i32()      # point size
    s.i32()      # weight
    s.u8()       # italic
    s.u8()       # underline
    s.u8()       # strikeout
    s.color()


def read_floating_text(s: Stream) -> FloatingText:
    text = s.string()
    rect = s.rect()
    flags = s.u8()
    read_font_setting(s)
    return FloatingText(text, rect, flags)


@dataclass
class GuitarIn:
    system: int
    staff: int
    position: int
    data: int

    @property
    def staff_guitars(self) -> int:
        return (self.data >> 8) & 0xFF

    @property
    def slash_guitars(self) -> int:
        return self.data & 0xFF


def read_guitar_in(s: Stream) -> GuitarIn:
    return GuitarIn(s.u16(), s.u8(), s.u8(), s.u16())


@dataclass
class TempoMarker:
    system: int
    position: int
    data: int
    description: str

    # beat types: 0 half, 1 half., 2 quarter, 3 quarter., 4 8th, 5 8th.,
    # 6 16th, 7 16th., 8 32nd, 9 32nd.
    @property
    def type(self) -> int:
        return (self.data & 0x18000000) >> 27   # 0 hidden, 1 standard, 2 listesso, 3 alteration

    @property
    def beat_type(self) -> int:
        return (self.data & 0x7800000) >> 23

    @property
    def listesso_beat_type(self) -> int:
        return (self.data & 0x780000) >> 19

    @property
    def bpm(self) -> int:
        return self.data & 0xFFFF

    @property
    def triplet_feel(self) -> int:
        return (self.data & 0x70000) >> 16


def read_tempo_marker(s: Stream) -> TempoMarker:
    system = s.u16()
    position = s.u8()
    data = s.u32()
    desc = s.string()
    return TempoMarker(system, position, data, desc)


@dataclass
class Dynamic:
    system: int
    staff: int
    position: int
    data: int

    NOT_SET = 0xFF

    @property
    def staff_volume(self) -> int:
        return (self.data >> 8) & 0xFF

    @property
    def slash_volume(self) -> int:
        return self.data & 0xFF


def read_dynamic(s: Stream) -> Dynamic:
    return Dynamic(s.u16(), s.u8(), s.u8(), s.u16())


@dataclass
class AlternateEnding:
    system: int
    position: int
    data: int

    @property
    def numbers(self) -> List[int]:
        bits = (self.data >> 16) & 0xFFFF
        return [n for n in range(1, 9) if bits & (1 << (n - 1))]

    @property
    def da_capo(self) -> bool:
        return bool((self.data >> 16) & (1 << 8))

    @property
    def dal_segno(self) -> bool:
        return bool((self.data >> 16) & (1 << 9))

    @property
    def dal_segno_segno(self) -> bool:
        return bool((self.data >> 16) & (1 << 10))


def read_alternate_ending(s: Stream) -> AlternateEnding:
    return AlternateEnding(s.u16(), s.u8(), s.u32())


@dataclass
class Direction:
    position: int
    symbols: List[int]

    def decoded(self):
        """(symbol type, active symbol, repeat number) per symbol."""
        return [((v & 0xFF00) >> 8, (v & 0xC0) >> 6, v & 0x3F) for v in self.symbols]


def read_direction(s: Stream) -> Direction:
    pos = s.u8()
    return Direction(pos, s.small_vector_u16())


@dataclass
class ChordText:
    position: int
    name: ChordName


def read_chord_text(s: Stream) -> ChordText:
    pos = s.u8()
    return ChordText(pos, read_chord_name(s))


# Rhythm slash flags
SLASH_DOTTED = 0x01
SLASH_DOUBLE_DOTTED = 0x02
SLASH_REST = 0x04
SLASH_TIED = 0x08
SLASH_MUTED = 0x10
SLASH_STACCATO = 0x20
SLASH_SINGLE_NOTE = 0x40
SLASH_PICK_UP = 0x80
SLASH_PICK_DOWN = 0x100
SLASH_ARPEGGIO_UP = 0x200
SLASH_ARPEGGIO_DOWN = 0x400
SLASH_TRIPLET_FEEL_1 = 0x800
SLASH_TRIPLET_FEEL_2 = 0x1000
SLASH_MARCATO = 0x2000
SLASH_SFORZANDO = 0x4000
SLASH_SLIDE_IN_ABOVE = 0x8000
SLASH_SLIDE_IN_BELOW = 0x10000
SLASH_SLIDE_OUT_DOWN = 0x20000
SLASH_SLIDE_OUT_UP = 0x40000


@dataclass
class RhythmSlash:
    position: int
    beaming: int
    data: int

    @property
    def duration(self) -> int:
        return 1 << ((self.data >> 21) & 0x7)

    def has(self, flag: int) -> bool:
        return bool(self.data & flag)

    @property
    def dots(self) -> int:
        return 2 if self.has(SLASH_DOUBLE_DOTTED) else 1 if self.has(SLASH_DOTTED) else 0

    @property
    def single_note(self):
        """(string, fret) for a single-note slash, else None."""
        if not self.has(SLASH_SINGLE_NOTE):
            return None
        return (self.data >> 24) & 0x7, (self.data >> 27) & 0x1F

    @property
    def triplet_start(self) -> bool:
        return bool(self.beaming & 0x20)

    @property
    def triplet_end(self) -> bool:
        return bool(self.beaming & 0x80)

    @property
    def beam_start(self) -> bool:
        return bool(self.beaming & 0x04)

    @property
    def beam_end(self) -> bool:
        return bool(self.beaming & 0x10)


def read_rhythm_slash(s: Stream) -> RhythmSlash:
    return RhythmSlash(s.u8(), s.u8(), s.u32())


@dataclass
class KeySignature:
    data: int

    @property
    def minor(self) -> bool:
        return bool(self.data & 0x40)

    @property
    def accidentals(self) -> int:
        """0 = none, 1-7 = sharps, 8-14 = 1-7 flats."""
        return self.data & 0x0F

    @property
    def shown(self) -> bool:
        return bool(self.data & 0x10)

    @property
    def cancellation(self) -> bool:
        return bool(self.data & 0x20)

    @property
    def fifths(self) -> int:
        """Circle-of-fifths value: +sharps / -flats."""
        a = self.accidentals
        return a if a <= 7 else -(a - 7)


@dataclass
class TimeSignature:
    data: int
    pulses: int

    @property
    def common_time(self) -> bool:
        return bool(self.data & 0x400000)

    @property
    def cut_time(self) -> bool:
        return bool(self.data & 0x800000)

    @property
    def shown(self) -> bool:
        return bool(self.data & 0x100000)

    @property
    def beats(self) -> int:
        if self.common_time:
            return 4
        if self.cut_time:
            return 2
        return ((self.data & 0xF8000000) >> 27) + 1

    @property
    def beat_value(self) -> int:
        if self.common_time:
            return 4
        if self.cut_time:
            return 2
        return 1 << ((self.data & 0x07000000) >> 24)


@dataclass
class RehearsalSign:
    letter: int
    description: str

    @property
    def is_set(self) -> bool:
        return self.letter != 0x7F


@dataclass
class Barline:
    position: int
    data: int
    key: KeySignature
    time: TimeSignature
    rehearsal: RehearsalSign

    BAR, DOUBLE, FREETIME, REPEAT_START, REPEAT_END, FINE = range(6)

    @property
    def type(self) -> int:
        return (self.data & 0xE0) >> 5

    @property
    def repeat_count(self) -> int:
        return self.data & 0x1F


def read_barline(s: Stream) -> Barline:
    pos = s.u8()
    data = s.u8()
    key = KeySignature(s.u8())
    time = TimeSignature(s.u32(), s.u8())
    letter = s.i8()
    desc = s.string()
    return Barline(pos, data, key, time, RehearsalSign(letter, desc))


# Note simple flags
TIED = 0x01
MUTED = 0x02
TIE_WRAP = 0x04
HAMMER_ON = 0x08
PULL_OFF = 0x10
HAMMER_PULL_NOWHERE = 0x20
NATURAL_HARMONIC = 0x40
GHOST = 0x80
OCTAVE_8VA = 0x100
OCTAVE_15MA = 0x200
OCTAVE_8VB = 0x400
OCTAVE_15MB = 0x800


@dataclass
class Note:
    string_data: int
    simple: int
    complex: List[int]

    @property
    def string(self) -> int:
        """Zero-based string, 0 = highest."""
        return (self.string_data & 0xE0) >> 5

    @property
    def fret(self) -> int:
        return self.string_data & 0x1F

    def has(self, flag: int) -> bool:
        return bool(self.simple & flag)

    @property
    def hammer_on(self) -> bool:
        return self.has(HAMMER_ON) and not self.has(HAMMER_PULL_NOWHERE)

    @property
    def pull_off(self) -> bool:
        return self.has(PULL_OFF) and not self.has(HAMMER_PULL_NOWHERE)

    @property
    def slide(self):
        """(slide-into type, slide-out-of type, steps) or None.

        into: 1 from below, 2 from above, 3/4 shift slide up/down,
              5/6 legato slide up/down
        out:  1 shift slide, 2 legato slide, 3 downwards, 4 upwards
        """
        v = _find_complex(self.complex, "d")
        if v is None:
            return None
        steps = v & 0xFF
        if steps > 127:
            steps -= 256
        return (v & 0xFF0000) >> 16, (v & 0xFF00) >> 8, steps

    @property
    def bend(self):
        """(type, bent pitch, release pitch, duration) in quarter tones, or None."""
        v = _find_complex(self.complex, "e")
        if v is None:
            return None
        return (v & 0xF00000) >> 20, (v & 0xF0) >> 4, v & 0xF, (v >> 8) & 0xFF

    @property
    def tapped_harmonic(self) -> Optional[int]:
        v = _find_complex(self.complex, "f")
        return None if v is None else v & 0xFF

    @property
    def trill(self) -> Optional[int]:
        v = _find_complex(self.complex, "g")
        return None if v is None else (v >> 16) & 0xFF

    @property
    def artificial_harmonic(self):
        v = _find_complex(self.complex, "h")
        if v is None:
            return None
        return v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF


def read_note(s: Stream) -> Note:
    string_data = s.u8()
    simple = s.u16()
    cx = s.small_vector_u32()
    if len(cx) > 3:
        raise PtbError(f"too many note symbols at offset {s.pos}")
    return Note(string_data, simple, cx)


# Position simple flags
DOTTED = 0x01
DOUBLE_DOTTED = 0x02
REST = 0x04
VIBRATO = 0x08
WIDE_VIBRATO = 0x10
ARPEGGIO_UP = 0x20
ARPEGGIO_DOWN = 0x40
PICK_UP = 0x80
PICK_DOWN = 0x100
STACCATO = 0x200
MARCATO = 0x400
SFORZANDO = 0x800
TREMOLO_PICKING = 0x1000
PALM_MUTE = 0x2000
TAP = 0x4000
APPOGGIATURA = 0x8000
ACCIACCATURA = 0x10000
TRIPLET_FEEL_1 = 0x20000
TRIPLET_FEEL_2 = 0x40000
LET_RING = 0x80000
FERMATA = 0x100000
GROUP_START = 0x200000
GROUP_MIDDLE = 0x400000
GROUP_END = 0x800000


@dataclass
class Position:
    position: int
    beaming: int
    data: int
    complex: List[int]
    notes: List[Note]

    @property
    def duration(self) -> int:
        """1, 2, 4, 8, 16, 32 or 64."""
        return (self.data >> 24) & 0xFF

    def has(self, flag: int) -> bool:
        return bool(self.data & flag)

    @property
    def dots(self) -> int:
        return 2 if self.has(DOUBLE_DOTTED) else 1 if self.has(DOTTED) else 0

    @property
    def is_rest(self) -> bool:
        return self.has(REST)

    @property
    def beam_start(self) -> bool:
        return bool(self.beaming & 0x400)

    @property
    def beam_end(self) -> bool:
        return bool(self.beaming & 0x2000)

    @property
    def tuplet(self):
        """(notes played, played over) for the start of an irregular group."""
        return ((self.beaming & 0x78) >> 3) + 1, (self.beaming & 0x07) + 1

    @property
    def multibar_rest(self) -> Optional[int]:
        v = _find_complex(self.complex, "j")
        return None if v is None else v & 0xFF

    @property
    def tremolo_bar(self):
        v = _find_complex(self.complex, "c")
        if v is None:
            return None
        return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF  # type, duration, pitch

    @property
    def volume_swell(self):
        v = _find_complex(self.complex, "a")
        if v is None:
            return None
        return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF  # start, end, duration


def read_position(s: Stream) -> Position:
    pos = s.u8()
    beaming = s.u16()
    data = s.u32()
    if (data >> 24) not in (1, 2, 4, 8, 16, 32, 64):
        raise PtbError(f"bad duration {data >> 24} at offset {s.pos}")
    cx = s.small_vector_u32()
    if len(cx) > 2:
        raise PtbError(f"too many position symbols at offset {s.pos}")
    notes = s.vector(read_note)
    return Position(pos, beaming, data, cx, notes)


@dataclass
class Staff:
    data: int
    voices: List[List[Position]]

    @property
    def clef(self) -> int:
        """0 = treble, 1 = bass."""
        return (self.data & 0xF0) >> 4

    @property
    def string_count(self) -> int:
        return self.data & 0x0F


def read_staff(s: Stream) -> Staff:
    data = s.u8()
    if not 3 <= (data & 0x0F) <= 7:
        raise PtbError(f"bad string count {data & 0x0F} at offset {s.pos}")
    s.skip(4)  # spacing values
    voices = [s.vector(read_position) for _ in range(2)]
    return Staff(data, voices)


@dataclass
class System:
    rect: tuple
    end_bar_data: int
    position_spacing: int
    start_bar: Barline
    directions: List[Direction]
    chord_texts: List[ChordText]
    rhythm_slashes: List[RhythmSlash]
    staves: List[Staff]
    barlines: List[Barline]

    @property
    def end_bar_type(self) -> int:
        return (self.end_bar_data & 0xE0) >> 5

    @property
    def end_bar_repeat_count(self) -> int:
        return self.end_bar_data & 0x1F

    def position_from_x(self, x: int) -> int:
        """Nearest position for a page x coordinate (port of GetPositionFromX)."""
        key = self.start_bar.key
        key_width = 0
        if key.shown:
            key_width = 6 * (key.accidentals - 7 if key.accidentals > 7 else key.accidentals)
        time_width = 18 if self.start_bar.time.shown else 0
        first = 22 + key_width + time_width + (3 if key_width and time_width else 0)
        first += 1 if self.start_bar.type == Barline.BAR else self.position_spacing
        spacing = max(self.position_spacing, 1)
        offset = x - self.rect[0] - first
        return max(0, offset // spacing - 1)


def read_system(s: Stream) -> System:
    rect = s.rect()
    end_bar = s.u8()
    spacing = s.u8()
    s.skip(3)  # slash spacing above/below, extra spacing
    start_bar = read_barline(s)
    directions = s.vector(read_direction)
    chord_texts = s.vector(read_chord_text)
    slashes = s.vector(read_rhythm_slash)
    staves = s.vector(read_staff)
    barlines = s.vector(read_barline)
    return System(rect, end_bar, spacing, start_bar, directions, chord_texts,
                  slashes, staves, barlines)


@dataclass
class Score:
    guitars: List[Guitar]
    chord_diagrams: List[ChordDiagram]
    floating_texts: List[FloatingText]
    guitar_ins: List[GuitarIn]
    tempo_markers: List[TempoMarker]
    dynamics: List[Dynamic]
    alternate_endings: List[AlternateEnding]
    systems: List[System]

    @property
    def is_empty(self) -> bool:
        return not any(p.notes or p.is_rest
                       for sys in self.systems for st in sys.staves
                       for v in st.voices for p in v) \
            and not any(sys.rhythm_slashes for sys in self.systems)


def read_score(s: Stream) -> Score:
    return Score(
        guitars=s.vector(read_guitar),
        chord_diagrams=s.vector(read_chord_diagram),
        floating_texts=s.vector(read_floating_text),
        guitar_ins=s.vector(read_guitar_in),
        tempo_markers=s.vector(read_tempo_marker),
        dynamics=s.vector(read_dynamic),
        alternate_endings=s.vector(read_alternate_ending),
        systems=s.vector(read_system),
    )


@dataclass
class Document:
    header: Header
    guitar_score: Score
    bass_score: Score


def parse_bytes(data: bytes) -> Document:
    return parse_stream(Stream(data))


def parse_stream(s: Stream) -> Document:
    header = read_header(s)
    guitar = read_score(s)
    bass = read_score(s)
    for _ in range(3):
        read_font_setting(s)
    s.i32()  # tablature staff line spacing
    s.u32()  # fade in
    s.u32()  # fade out
    if s.data[s.pos:].strip(b"\0"):
        raise PtbError(f"unexpected data after the end of the song at offset {s.pos}")
    return Document(header, guitar, bass)


def parse_file(path) -> Document:
    with open(path, "rb") as f:
        return parse_bytes(f.read())
