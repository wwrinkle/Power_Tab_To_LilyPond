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

"""Convert a parsed Power Tab document into LilyPond source.

Layout of a generated file:

  * A comment block explaining how to read the music, and shorthand
    definitions for guitar effects (\\pmOn, \\bendUp, ...).
  * Per score (guitar, bass):
      - `<score>Global`: time/key signatures, bar lines and bar lengths,
        shared by every staff so the staves stay in step.
      - `<score>Marks`: tempo, section letters, repeat endings, directions,
        chord names and floating text, printed once above the score.
      - `<score>Slashes`: rhythm slashes, if the score has any.
      - `<score>StaffI`, `<score>StaffII`, ...: the notes of each staff,
        one line per bar, used by both the notation staff and the tab staff.

Power Tab stores music as numbered slots ("positions") on each line of
music; the converter turns them into bars of real durations. Every staff
gets the same bar lengths (short voices are padded with invisible rests), so
mis-counted bars in the source can't knock the staves out of sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Tuple, Union

from . import ptbparser as P

# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

SHARP_NAMES = ["c", "cis", "d", "dis", "e", "f", "fis", "g", "gis", "a", "ais", "b"]
FLAT_NAMES = ["c", "des", "d", "es", "e", "f", "ges", "g", "as", "a", "bes", "b"]
SHARP_TEXT = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_TEXT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# LilyPond tonic for each key signature (index = fifths + 7)
MAJOR_KEYS = ["ces", "ges", "des", "as", "es", "bes", "f", "c",
              "g", "d", "a", "e", "b", "fis", "cis"]
MINOR_KEYS = ["as", "es", "bes", "f", "c", "g", "d", "a",
              "e", "b", "fis", "cis", "gis", "dis", "ais"]

# Tempo marker beat types
TEMPO_BEATS = ["2", "2.", "4", "4.", "8", "8.", "16", "16.", "32", "32."]

TRIPLET_FEEL_TEXT = {1: ("8", "Triplet feel"), 2: ("16", "Triplet feel"),
                     3: ("8", "Triplet feel (off-beat)"), 4: ("16", "Triplet feel (off-beat)")}

DYNAMICS = {104: "fff", 91: "ff", 78: "f", 65: "mf", 52: "mp",
            39: "p", 26: "pp", 13: "ppp"}

DIRECTION_TEXT = {
    4: "Fine", 5: "D.C.", 6: "D.S.", 7: "D.S.S.", 8: "To Coda",
    9: "To Double Coda", 10: "D.C. al Coda", 11: "D.C. al Double Coda",
    12: "D.S. al Coda", 13: "D.S. al Double Coda", 14: "D.S.S. al Coda",
    15: "D.S.S. al Double Coda", 16: "D.C. al Fine", 17: "D.S. al Fine",
    18: "D.S.S. al Fine",
}
DIRECTION_GLYPH = {0: "scripts.coda", 1: "scripts.varcoda",
                   2: "scripts.segno", 3: "scripts.segno"}
DIRECTION_ACTIVE = {1: "on D.C.", 2: "on D.S.", 3: "on D.S.S."}

BAR_GLYPHS = {
    P.Barline.BAR: "|",
    P.Barline.DOUBLE: "||",
    P.Barline.FREETIME: "!",
    P.Barline.REPEAT_START: ".|:",
    P.Barline.REPEAT_END: ":|.",
    P.Barline.FINE: "|.",
}

# Whammy bar types, in Power Tab's order: the shorthand that draws each one,
# and the sign written before the amount.
WHAMMY = [("wDip", "−"), ("wDive", "−"), ("wDiveHold", "−"), ("wRelease", ""),
          ("wReturn", ""), ("wReturnHold", ""), ("wInvDip", "+")]

# Where an artificial harmonic is touched, in frets above the fretted note,
# by how far above it sounds: an octave at 12 frets, octave + fifth at 7, ...
HARMONIC_TOUCH = {12: 12, 19: 7, 24: 5, 28: 4}

OCTAVE_TEXT = {12: " 8va", 24: " 15ma"}

AUDIO_RELEASE = ["single", "EP", "album", "double album", "triple album", "box set"]

MUSIC_STYLES = ["Alternative", "Bluegrass", "Blues", "Country", "Fingerpicking",
                "Flamenco", "Folk", "Funk", "Fusion", "General", "Jazz", "Metal",
                "Other", "Pop", "Progressive", "Punk", "Reggae", "Rock", "Swing"]
LESSON_LEVELS = ["Beginner", "Intermediate", "Advanced"]

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
         "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII",
         "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX", "XXX", "XXXI"]

# General MIDI programs, as LilyPond names them (scm/midi.scm).
GM_INSTRUMENTS = [
    "acoustic grand", "bright acoustic", "electric grand", "honky-tonk",
    "electric piano 1", "electric piano 2", "harpsichord", "clav", "celesta",
    "glockenspiel", "music box", "vibraphone", "marimba", "xylophone",
    "tubular bells", "dulcimer", "drawbar organ", "percussive organ",
    "rock organ", "church organ", "reed organ", "accordion", "harmonica",
    "concertina", "acoustic guitar (nylon)", "acoustic guitar (steel)",
    "electric guitar (jazz)", "electric guitar (clean)",
    "electric guitar (muted)", "overdriven guitar", "distorted guitar",
    "guitar harmonics", "acoustic bass", "electric bass (finger)",
    "electric bass (pick)", "fretless bass", "slap bass 1", "slap bass 2",
    "synth bass 1", "synth bass 2", "violin", "viola", "cello", "contrabass",
    "tremolo strings", "pizzicato strings", "orchestral harp", "timpani",
    "string ensemble 1", "string ensemble 2", "synthstrings 1",
    "synthstrings 2", "choir aahs", "voice oohs", "synth voice",
    "orchestra hit", "trumpet", "trombone", "tuba", "muted trumpet",
    "french horn", "brass section", "synthbrass 1", "synthbrass 2",
    "soprano sax", "alto sax", "tenor sax", "baritone sax", "oboe",
    "english horn", "bassoon", "clarinet", "piccolo", "flute", "recorder",
    "pan flute", "blown bottle", "shakuhachi", "whistle", "ocarina",
    "lead 1 (square)", "lead 2 (sawtooth)", "lead 3 (calliope)",
    "lead 4 (chiff)", "lead 5 (charang)", "lead 6 (voice)", "lead 7 (fifths)",
    "lead 8 (bass+lead)", "pad 1 (new age)", "pad 2 (warm)",
    "pad 3 (polysynth)", "pad 4 (choir)", "pad 5 (bowed)", "pad 6 (metallic)",
    "pad 7 (halo)", "pad 8 (sweep)", "fx 1 (rain)", "fx 2 (soundtrack)",
    "fx 3 (crystal)", "fx 4 (atmosphere)", "fx 5 (brightness)",
    "fx 6 (goblins)", "fx 7 (echoes)", "fx 8 (sci-fi)", "sitar", "banjo",
    "shamisen", "koto", "kalimba", "bagpipe", "fiddle", "shanai",
    "tinkle bell", "agogo", "steel drums", "woodblock", "taiko drum",
    "melodic tom", "synth drum", "reverse cymbal", "guitar fret noise",
    "breath noise", "seashore", "bird tweet", "telephone ring", "helicopter",
    "applause", "gunshot",
]

STANDARD_TUNINGS = {4: [43, 38, 33, 28], 5: [43, 38, 33, 28, 23],
                    6: [64, 59, 55, 50, 45, 40], 7: [64, 59, 55, 50, 45, 40, 35]}

# Shorthands written at the top of every file, so the music stays readable.
SHORTHANDS = r"""%% Shorthands for guitar effects used in the music below.
% A small label above a note. Labels take up room on the line, so the notes
% spread out instead of the labels piling up, e.g. \noteLabel "full".
noteLabel = #(define-event-function (text) (markup?)
  #{ -\tweak extra-spacing-width #'(-0.2 . 0.2)
     -\tweak extra-spacing-height #'(-inf.0 . +inf.0)
     ^\markup \small #text #})
% A text label, e.g. \fx "T.H.".
fx = #(define-event-function (text) (markup?) #{ \noteLabel #text #})
% Bends: an arrow and the amount ("full" = a whole step), e.g. \bendUp "full".
bendUp = #(define-event-function (text) (markup?)
  #{ \noteLabel \markup \concat { \fontsize #-5 \arrow-head #Y #UP ##f " " #text } #})
bendDown = #(define-event-function (text) (markup?)
  #{ \noteLabel \markup \concat { \fontsize #-5 \arrow-head #Y #DOWN ##f " " #text } #})
% Trill with the fret to trill to, e.g. \trillTo "7".
trillTo = #(define-event-function (fret) (markup?)
  #{ \noteLabel \markup \line { \musicglyph "scripts.trill" \concat { "(" #fret ")" } } #})
% Palm muting: a dashed "P.M." line from \pmOn to \pmOff (\pm on one note).
pmOn = -\tweak bound-details.left.text \markup \small \italic "P.M." \startTextSpan
pmOff = \stopTextSpan
pm = ^\markup \small \italic "P.M."
% Vibrato: a wavy line from \vibOn (or \wideVibOn) to \vibOff.
vibOn = -\tweak bound-details.left.text ##f \startTrillSpan
wideVibOn = -\tweak bound-details.left.text \markup \small "wide" \startTrillSpan
vibOff = \stopTrillSpan
letRing = ^\markup \small \italic "let ring"
% Slide into a note: an invisible grace note a couple of frets away, joined
% to the note by a slide line. Used as \slideIn <f\3>16\glissando <a\3>4.
slideIn = #(define-music-function (from) (ly:music?)
  #{ \grace { \hideNotes #from \unHideNotes } #})
% Chord name above the music, e.g. \chord "Em7".
chord = #(define-event-function (text) (markup?) #{ ^\markup \upright \bold #text #})
% Artificial or tapped harmonic: a diamond note head, and in the tab the fret
% held with the fret touched or tapped in brackets, e.g. \harm "7(19)" b\3.
harm = #(define-music-function (tab note) (markup? ly:music?)
  #{ \tweak NoteHead.style #'harmonic
     \tweak TabNoteHead.stencil #(lambda (grob) (grob-interpret-markup grob tab))
     #note #})
% Whammy bar: a small graph of the pitch with the amount above it, in steps,
% e.g. \wDip "−½" (a quick dip of a half step and back).
#(define (whammy graph)
   (define-event-function (amount) (markup?)
     #{ \noteLabel \markup \center-column { #amount \path #0.15 #graph } #}))
wDip = #(whammy '((moveto 0 1) (lineto 1.2 0) (lineto 2.4 1)))
wInvDip = #(whammy '((moveto 0 0) (lineto 1.2 1) (lineto 2.4 0)))
wDive = #(whammy '((moveto 0 1) (lineto 2.4 0)))
wDiveHold = #(whammy '((moveto 0 1) (lineto 1.6 0) (lineto 2.4 0)))
wReturn = #(whammy '((moveto 0 0) (lineto 2.4 1)))
wReturnHold = #(whammy '((moveto 0 0) (lineto 1.6 1) (lineto 2.4 1)))
wRelease = #(whammy '((moveto 0 0) (lineto 0.6 0) (moveto 0.9 0) (lineto 1.5 0)
                       (moveto 1.8 0) (lineto 2.4 0)))
"""

# From the LilyPond documentation ("Transposing pitches with minimum
# accidentals"): respells pitches after \transpose so there are no double or
# triple sharps/flats, and no E#, B#, Cb or Fb.
NATURALIZE = r"""% \naturalizeMusic: after transposing the notation, respell notes with the
% fewest accidentals (no double sharps, no E#, B#, Cb or Fb).
#(define (naturalize-pitch p)
   (let ((o (ly:pitch-octave p))
         (a (* 4 (ly:pitch-alteration p)))
         (n (ly:pitch-notename p)))
     (cond
      ((and (> a 1) (or (eq? n 6) (eq? n 2)))
       (set! a (- a 2)) (set! n (+ n 1)))
      ((and (< a -1) (or (eq? n 0) (eq? n 3)))
       (set! a (+ a 2)) (set! n (- n 1))))
     (cond
      ((> a 2) (set! a (- a 4)) (set! n (+ n 1)))
      ((< a -2) (set! a (+ a 4)) (set! n (- n 1))))
     (if (< n 0) (begin (set! o (- o 1)) (set! n (+ n 7))))
     (if (> n 6) (begin (set! o (+ o 1)) (set! n (- n 7))))
     (ly:make-pitch o n (/ a 4))))

#(define (naturalize music)
   (let ((es (ly:music-property music 'elements))
         (e (ly:music-property music 'element))
         (p (ly:music-property music 'pitch)))
     (if (pair? es)
         (ly:music-set-property! music 'elements (map naturalize es)))
     (if (ly:music? e)
         (ly:music-set-property! music 'element (naturalize e)))
     (if (ly:pitch? p)
         (ly:music-set-property! music 'pitch (naturalize-pitch p)))
     music))

naturalizeMusic = #(define-music-function (m) (ly:music?) (naturalize m))
"""

READING_GUIDE = r"""% How to read the music below:
%   <e,\6>8        one note: pitch e, on string 6 (\6), eighth note
%   <e\4 b\3>4     a chord: one pitch per string
%   ~  ( )  [ ]    tie, slur (hammer-on/pull-off), beam
%   r4  R4*4       a rest; a whole-bar rest 4 beats long
%   s4*3           an invisible spacer, 3 beats long
%   | % bar 12     a bar line; bar numbers match the printed score
% Pitches are the sounding pitches; the tab staff works out the frets from
% the pitch and the string number.
"""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def pitch_name(midi: int, flats: bool) -> str:
    names = FLAT_NAMES if flats else SHARP_NAMES
    octave = midi // 12 - 4
    marks = "'" * octave if octave > 0 else "," * (-octave)
    return names[midi % 12] + marks


def note_text(midi: int, sharps: bool = True) -> str:
    return (SHARP_TEXT if sharps else FLAT_TEXT)[midi % 12]


def duration_str(dur: int, dots: int) -> str:
    return str(dur) + "." * dots


def length_str(length: Fraction, beat_value: int) -> str:
    """A LilyPond duration for a span, in beats where possible: "4*3"."""
    beats = length * beat_value
    if beats.denominator == 1:
        return f"{beat_value}*{beats.numerator}"
    return f"1*{length.numerator}/{length.denominator}"


def ly_string(text: str) -> str:
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = " ".join(text.split())
    return f'"{text}"'


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def quarter_steps(q: int) -> str:
    """A pitch amount in quarter steps as guitar players write it."""
    if q == 4:
        return "full"
    whole, rem = divmod(q, 4)
    frac = {1: "¼", 2: "½", 3: "¾"}.get(rem, "")
    return (str(whole) if whole else "") + frac


def bend_markup(bend) -> str:
    """The \\bendUp / \\bendDown post-event for a note's bend."""
    btype, bent, release, _ = bend
    up = quarter_steps(bent) if bent else "full"
    if btype in (6, 7):                       # gradual / immediate release
        down = quarter_steps(release) if release else ""
        return f'\\bendDown {ly_string(("rel. " + down).strip())}'
    text = {0: up, 1: up + " & rel.", 2: up + " & hold", 3: "pre " + up,
            4: "pre " + up + " & rel.", 5: "pre " + up + " & hold"}.get(btype, up)
    return f"\\bendUp {ly_string(text)}"


GLUED = ("[", "]", "(", ")")


def unique(items: Sequence[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def volume_dynamic(volume: int) -> str:
    """Closest dynamic at or below a MIDI volume (as PTE 2.0 does)."""
    for level in (104, 91, 78, 65, 52, 39, 26):
        if volume >= level:
            return DYNAMICS[level]
    return "ppp"


def chord_text(name: P.ChordName) -> str:
    text = name.text()
    extras = []
    if name.fret_position:                       # fret 1 -> "I", fret 5 -> "V"
        extras.append(ROMAN[name.fret_position - 1])
    if name.chord_type is not None:
        extras.append(f"type {name.chord_type}")
    if extras:
        text += " (" + ", ".join(extras) + ")"
    return text


def tuning_text(tuning: P.Tuning) -> str:
    notes = " ".join(note_text(n, tuning.sharps) for n in reversed(tuning.notes))
    return f"{tuning.name.strip() or 'Tuning'} ({notes})"


# ---------------------------------------------------------------------------
# Options and intermediate model
# ---------------------------------------------------------------------------

@dataclass
class Options:
    lyrics: bool = True            # print the lyrics text after the score
    midi: bool = False             # add a MIDI score
    keep_systems: bool = False     # break lines where Power Tab did
    source_name: str = ""          # file name, for the header comment


@dataclass
class NoteOut:
    pitch: int
    string: int                    # 1-based for LilyPond
    tie: bool = False              # tied to the next note
    repeat_tie: bool = False       # tied from a note that isn't adjacent
    dead: bool = False
    ghost: bool = False
    harmonic: bool = False
    tab_text: Optional[str] = None  # artificial/tapped harmonic, e.g. "7(19)"


Source = Union[P.Position, P.RhythmSlash, None]


@dataclass
class Event:
    position: int
    length: Fraction               # in whole notes (0 for grace notes)
    duration: str                  # LilyPond duration, e.g. "8."
    rest: bool
    source: Source = None
    slash: bool = False
    grace: Optional[str] = None    # "acciaccatura" or "appoggiatura"
    notes: List[NoteOut] = field(default_factory=list)
    full_bar_rest: Optional[Fraction] = None
    tuplet_open: Optional[str] = None
    tuplet_close: bool = False
    pre: List[str] = field(default_factory=list)
    post: List[str] = field(default_factory=list)
    harmonic_fret: Optional[int] = None
    slide_in: List[Tuple[int, int]] = field(default_factory=list)   # (pitch, string)
    glissando: bool = False        # slide to the next note
    slur: bool = False             # slur to the next note
    pm: bool = False
    let_ring: bool = False
    vibrato: int = 0               # 0 none, 1 normal, 2 wide
    ottava: int = 0
    swell: int = 0                 # +1 crescendo, -1 decrescendo
    harmonic_label: Optional[str] = None   # "A.H. 8va", "T.H.", ...
    whammy: Optional[Tuple[str, str]] = None   # (shorthand, amount)
    tremolo: bool = False
    beam_start: bool = False
    beam_end: bool = False


@dataclass
class VoiceBar:
    events: List[Event] = field(default_factory=list)
    length: Fraction = Fraction(0)
    is_full_rest: bool = False


@dataclass
class Bar:
    system_index: int
    start_pos: int
    end_pos: int                   # exclusive
    start_barline: P.Barline
    closing_bar: int               # barline type at the end of the bar
    closing_repeat_count: int
    nominal: Fraction
    length: Fraction = Fraction(0)
    multibar: int = 1
    rehearsal: Optional[P.RehearsalSign] = None
    voices: List[List[VoiceBar]] = field(default_factory=list)   # [staff][voice]
    slashes: VoiceBar = field(default_factory=VoiceBar)
    pos_offsets: Dict[int, Fraction] = field(default_factory=dict)

    @property
    def beat_value(self) -> int:
        return self.start_barline.time.beat_value


@dataclass
class TimedItem:
    """What the timing code needs from a position or a rhythm slash."""
    position: int
    duration: int
    dots: int
    rest: bool
    grace: Optional[str]
    tuplet_start: Optional[Tuple[int, int]]
    tuplet_end: bool
    source: Source


def position_item(p: P.Position) -> TimedItem:
    grace = ("appoggiatura" if p.has(P.APPOGGIATURA)
             else "acciaccatura" if p.has(P.ACCIACCATURA) else None)
    return TimedItem(p.position, p.duration, p.dots, p.is_rest or not p.notes, grace,
                     p.tuplet if p.has(P.GROUP_START) else None,
                     p.has(P.GROUP_END), p)


def slash_item(s: P.RhythmSlash) -> TimedItem:
    return TimedItem(s.position, s.duration, s.dots, s.has(P.SLASH_REST), None,
                     (3, 2) if s.triplet_start else None, s.triplet_end, s)


# ---------------------------------------------------------------------------
# Score converter
# ---------------------------------------------------------------------------

class ScoreConverter:
    def __init__(self, score: P.Score, prefix: str, options: Options):
        self.score = score
        self.prefix = prefix
        self.options = options
        self.num_staves = max((len(s.staves) for s in score.systems), default=0)
        self.has_slashes = any(s.rhythm_slashes for s in score.systems)
        self.bars: List[Bar] = []
        self.staff_guitars: List[List[List[int]]] = []     # [system][staff]
        self.guitar_changes: Dict[Tuple[int, int, int], List[int]] = {}
        self.tagged_staves = set()    # staves whose music has notation/tab-only tags
        self.transposed = False       # some staff's notation is transposed
        self.flats = False

    # -- guitars and tunings ------------------------------------------------

    def assign_guitars(self) -> None:
        """Track which guitar plays on each staff (from Guitar In symbols)."""
        ins_by_system: Dict[int, List[P.GuitarIn]] = {}
        for gi in self.score.guitar_ins:
            ins_by_system.setdefault(gi.system, []).append(gi)
        current: Dict[int, List[int]] = {}
        for si, system in enumerate(self.score.systems):
            ins = sorted(ins_by_system.get(si, []), key=lambda g: (g.position, g.staff))
            first_pos = min((p.position for st in system.staves for v in st.voices for p in v),
                            default=0)
            later: Dict[int, List[int]] = {}
            for gi in ins:
                guitars = [b for b in range(8) if gi.staff_guitars & (1 << b)]
                if not guitars:
                    continue
                if gi.position <= first_pos:
                    current[gi.staff] = guitars
                else:
                    self.guitar_changes[(si, gi.staff, gi.position)] = guitars
                    later[gi.staff] = guitars
            snapshot = []
            for st in range(len(system.staves)):
                default = [st] if st < len(self.score.guitars) else [0]
                snapshot.append(list(current.get(st, default)))
            self.staff_guitars.append(snapshot)
            current.update(later)       # mid-system changes carry on

    def guitar(self, number: int) -> Optional[P.Guitar]:
        for g in self.score.guitars:
            if g.number == number:
                return g
        return self.score.guitars[0] if self.score.guitars else None

    def guitars_on(self, si: int, staff: int) -> List[int]:
        row = self.staff_guitars[si]
        return row[staff] if staff < len(row) else [0]

    def tuning_for(self, si: int, staff: int, string_count: int) -> Tuple[List[int], int, int]:
        """(MIDI notes high->low, capo, notation offset) for a staff in a system.

        When several guitars share a staff, the first one whose string count
        matches is used, as in Power Tab Editor.
        """
        guitars = self.guitars_on(si, staff)
        for num in guitars:
            g = self.guitar(num)
            if g and len(g.tuning.notes) == string_count:
                return g.tuning.notes, g.capo, g.tuning.notation_offset
        g = self.guitar(guitars[0]) if guitars else None
        if g and len(g.tuning.notes) >= string_count:
            return g.tuning.notes[:string_count], g.capo, g.tuning.notation_offset
        fallback = STANDARD_TUNINGS.get(string_count, STANDARD_TUNINGS[6][:string_count])
        return fallback, 0, 0

    # -- bars ---------------------------------------------------------------

    def build_bars(self) -> None:
        pending_rehearsal: Optional[P.RehearsalSign] = None
        for si, system in enumerate(self.score.systems):
            barlines = sorted(system.barlines, key=lambda b: b.position)
            starts = [system.start_bar] + barlines
            last_pos = max([p.position for st in system.staves for v in st.voices for p in v]
                           + [s.position for s in system.rhythm_slashes]
                           + [c.position for c in system.chord_texts]
                           + [d.position for d in system.directions]
                           + [b.position for b in barlines] + [0])
            for bi, bl in enumerate(starts):
                start = 0 if bi == 0 else bl.position
                if bi + 1 < len(starts):
                    end = starts[bi + 1].position
                    closing, count = starts[bi + 1].type, starts[bi + 1].repeat_count
                else:
                    end = last_pos + 1
                    closing, count = system.end_bar_type, system.end_bar_repeat_count
                bar = Bar(si, start, end, bl, closing, count,
                          Fraction(bl.time.beats, bl.time.beat_value))
                bar.rehearsal = bl.rehearsal if bl.rehearsal.is_set else pending_rehearsal
                pending_rehearsal = None
                self.fill_bar(bar, system)
                empty = all(not vb.events for staff in bar.voices for vb in staff) \
                    and not bar.slashes.events
                if empty and bi > 0 and bi == len(starts) - 1:
                    # A barline placed at the very end of the line leaves an
                    # empty region after it: not a real bar.
                    previous = self.bars[-1] if self.bars else None
                    if previous and previous.system_index == si and closing != P.Barline.BAR:
                        # Keep the more interesting of the two bar lines.
                        previous.closing_bar = closing
                        previous.closing_repeat_count = count
                    pending_rehearsal = bar.rehearsal
                    continue
                if empty and bi > 0 and end - start <= 1:
                    # Two barlines in neighbouring slots (e.g. repeat end then
                    # repeat start) leave an empty sliver between them.
                    pending_rehearsal = bar.rehearsal
                    continue
                self.bars.append(bar)

    def fill_bar(self, bar: Bar, system: P.System) -> None:
        def in_bar(pos: int) -> bool:
            return bar.start_pos <= pos < bar.end_pos

        for st_index in range(self.num_staves):
            if st_index < len(system.staves):
                staff = system.staves[st_index]
                bar.voices.append([
                    self.time_events([position_item(p) for p in v if in_bar(p.position)], bar)
                    for v in staff.voices])
            else:
                bar.voices.append([VoiceBar(), VoiceBar()])
        bar.slashes = self.time_events(
            [slash_item(s) for s in system.rhythm_slashes if in_bar(s.position)], bar)
        for ev in bar.slashes.events:
            ev.slash = True

        all_voices = [vb for staff in bar.voices for vb in staff] + [bar.slashes]
        lengths = [vb.length for vb in all_voices if vb.events and not vb.is_full_rest]
        if lengths and max(lengths) > 0:
            bar.length = max(lengths)
        else:
            bar.multibar = max((vb.events[0].source.multibar_rest or 1
                                for vb in all_voices
                                if vb.is_full_rest and isinstance(vb.events[0].source, P.Position)),
                               default=1)
            bar.length = bar.nominal * bar.multibar
        for vb in all_voices:
            if vb.is_full_rest:
                vb.events[0].full_bar_rest = bar.length
        # Time offset of each position, for marks and chord names.
        for vb in all_voices:
            t = Fraction(0)
            for ev in vb.events:
                if ev.position not in bar.pos_offsets or t < bar.pos_offsets[ev.position]:
                    bar.pos_offsets[ev.position] = t
                t += ev.length

    @staticmethod
    def time_events(items: List[TimedItem], bar: Bar) -> VoiceBar:
        """Turn positions (or slashes) into timed events."""
        vb = VoiceBar()
        if not items:
            return vb
        first = items[0]
        multibar = isinstance(first.source, P.Position) and first.source.multibar_rest
        if len(items) == 1 and first.rest and (multibar or (first.duration == 1 and first.dots == 0)):
            vb.events.append(Event(first.position, bar.nominal, "1", True, source=first.source))
            vb.is_full_rest = True
            return vb
        factor: Optional[Fraction] = None
        for item in items:
            ev = Event(item.position, Fraction(0), "", item.rest, source=item.source,
                       grace=item.grace)
            if item.tuplet_start:
                if factor is not None:
                    vb.events[-1].tuplet_close = True
                    factor = None
                played, over = item.tuplet_start
                if played != over and played > 0 and over > 0:
                    ev.tuplet_open = f"{played}/{over}"
                    factor = Fraction(over, played)
            dur = item.duration if item.duration in (1, 2, 4, 8, 16, 32, 64) else 4
            ev.duration = duration_str(dur, item.dots)
            length = Fraction(1, dur) * (2 - Fraction(1, 2 ** item.dots))
            if factor is not None:
                length *= factor
            ev.length = Fraction(0) if item.grace else length
            vb.events.append(ev)
            vb.length += ev.length
            if factor is not None and item.tuplet_end:
                ev.tuplet_close = True
                factor = None
        if factor is not None:
            vb.events[-1].tuplet_close = True
        return vb

    # -- notes and effects --------------------------------------------------

    def fill_notes(self) -> None:
        previous: Dict[Tuple[int, int], Optional[Event]] = {}
        prev_slash: Optional[Event] = None
        for bar in self.bars:
            system = self.score.systems[bar.system_index]
            # "previous" is the note a tie could come from. A tie only works
            # between neighbouring notes, so anything in between (a rest, a
            # grace note, padding, a bar where the staff is missing) clears it.
            for st_index, staff_voices in enumerate(bar.voices):
                if st_index >= len(system.staves):
                    previous[(st_index, 0)] = previous[(st_index, 1)] = None
                    continue
                staff = system.staves[st_index]
                tuning, capo, _ = self.tuning_for(bar.system_index, st_index, staff.string_count)
                for v_index, vb in enumerate(staff_voices):
                    key = (st_index, v_index)
                    for ev in vb.events:
                        if ev.full_bar_rest is None:
                            self.fill_position(ev, tuning, capo, previous.get(key))
                        previous[key] = None if ev.rest or ev.grace or ev.full_bar_rest else ev
                    if vb.length < bar.length:
                        previous[key] = None
            for ev in bar.slashes.events:
                if ev.full_bar_rest is None:
                    self.fill_slash(ev, prev_slash)
                prev_slash = None if ev.rest or ev.full_bar_rest else ev
            if bar.slashes.length < bar.length:
                prev_slash = None

    def fill_position(self, ev: Event, tuning: List[int], capo: int,
                      previous: Optional[Event]) -> None:
        p = ev.source
        assert isinstance(p, P.Position)
        ev.beam_start, ev.beam_end = p.beam_start, p.beam_end
        if ev.rest:
            return
        labels: List[str] = []
        harmonic_frets = set()
        ties: List[Tuple[NoteOut, NoteOut]] = []     # (note tied from, note tied to)
        for n in sorted(p.notes, key=lambda n: -n.string):      # lowest string first
            if n.string >= len(tuning):
                continue
            out = NoteOut(tuning[n.string] + capo + n.fret, n.string + 1)
            out.dead = n.has(P.MUTED)
            out.ghost = n.has(P.GHOST)
            out.harmonic = n.has(P.NATURAL_HARMONIC)
            if out.harmonic:
                harmonic_frets.add(n.fret)
            self.note_harmonic(ev, n, out)
            if n.has(P.TIED) and not ev.grace:
                match = None
                # \harmonicByFret chords sound at another pitch: no tie out of them.
                if previous is not None and previous.harmonic_fret is None:
                    match = next((pn for pn in previous.notes
                                  if pn.string == out.string and pn.pitch == out.pitch), None)
                if match is not None:
                    match.tie = True
                    ties.append((match, out))
                else:
                    out.repeat_tie = True
            if n.has(P.HAMMER_PULL_NOWHERE):
                labels.append('\\fx "H"' if n.has(P.HAMMER_ON) else '\\fx "P"')
            elif n.has(P.HAMMER_ON) or n.has(P.PULL_OFF):
                ev.slur = True
            self.note_slide(ev, n, out, tuning, capo)
            if n.bend:
                labels.append(bend_markup(n.bend))
            if n.trill is not None:
                labels.append(f'\\trillTo "{n.trill}"')
            for flag, level in ((P.OCTAVE_8VA, 1), (P.OCTAVE_15MA, 2),
                                (P.OCTAVE_8VB, -1), (P.OCTAVE_15MB, -2)):
                if n.has(flag):
                    ev.ottava = level
            ev.notes.append(out)
        if not ev.notes:
            ev.rest = True
            return
        # All natural harmonics at one fret: LilyPond can show the sounding
        # pitch in the notation and the fret in the tab.
        if len(harmonic_frets) == 1 and all(n.harmonic for n in ev.notes):
            fret = harmonic_frets.pop()
            ev.harmonic_fret = fret
            for n in ev.notes:
                n.pitch -= fret
                n.harmonic = False
        if ev.harmonic_fret is not None or ev.slide_in:
            # The rewritten pitches, or the hidden slide-in grace note, would
            # break a normal tie: draw a short tie from the left instead.
            for tied_from, tied_to in ties:
                tied_from.tie = False
                tied_to.repeat_tie = True

        self.position_articulations(ev, p)
        ev.post.extend(labels)
        ev.pm = p.has(P.PALM_MUTE)
        ev.let_ring = p.has(P.LET_RING)
        ev.tremolo = p.has(P.TREMOLO_PICKING)
        ev.vibrato = 2 if p.has(P.WIDE_VIBRATO) else 1 if p.has(P.VIBRATO) else 0
        if p.has(P.TAP):
            ev.post.append('\\fx "T"')
        if p.tremolo_bar:
            ttype, _, pitch = p.tremolo_bar
            if ttype < len(WHAMMY):
                shorthand, sign = WHAMMY[ttype]
                # Amounts are in quarter steps: 4 is one whole step.
                amount = sign + ("1" if pitch == 4 else quarter_steps(pitch)) if pitch else ""
                ev.whammy = (shorthand, amount)
            else:
                ev.post.append('\\fx "w/bar"')
        if p.volume_swell:
            start, end, _ = p.volume_swell
            ev.swell = 1 if end >= start else -1

    @staticmethod
    def note_harmonic(ev: Event, n: P.Note, out: NoteOut) -> None:
        """Artificial and tapped harmonics: diamond heads, "7(19)" in the tab.

        The label ("A.H. 8va") says how far above the written note the
        harmonic sounds; it is printed once for a run of such notes.
        """
        if n.tapped_harmonic is not None:
            tapped = n.tapped_harmonic
            out.tab_text = f"{n.fret}({tapped})"
            ev.harmonic_label = "T.H." + OCTAVE_TEXT.get(tapped - n.fret, "")
        if n.artificial_harmonic is not None:
            key, _, octave = n.artificial_harmonic
            # Written as the harmonic's note at or above the fretted note,
            # sounding 0, 1 or 2 octaves higher.
            up = (key - out.pitch) % 12
            out.pitch += up
            touch = HARMONIC_TOUCH.get(up + 12 * octave)
            out.tab_text = f"{n.fret}({n.fret + touch})" if touch else str(n.fret)
            ev.harmonic_label = "A.H." + OCTAVE_TEXT.get(12 * octave, "")

    @staticmethod
    def note_slide(ev: Event, n: P.Note, out: NoteOut, tuning: List[int], capo: int) -> None:
        slide = n.slide
        if not slide:
            return
        into, out_of, _ = slide
        if out_of in (1, 2):                  # shift / legato slide to the next note
            ev.glissando = True
            if out_of == 2:
                ev.slur = True
        elif out_of == 3:
            ev.post.append("\\bendAfter #-4")
        elif out_of == 4:
            ev.post.append("\\bendAfter #+4")
        if into and not ev.grace:
            from_below = into in (1, 3, 5)
            fret = n.fret - 2 if from_below else n.fret + 2
            if fret >= 0:
                ev.slide_in.append((tuning[n.string] + capo + fret, out.string))

    @staticmethod
    def position_articulations(ev: Event, src) -> None:
        is_slash = isinstance(src, P.RhythmSlash)
        flags = (P.SLASH_STACCATO, P.SLASH_MARCATO, P.SLASH_SFORZANDO, None,
                 P.SLASH_PICK_DOWN, P.SLASH_PICK_UP, P.SLASH_ARPEGGIO_UP,
                 P.SLASH_ARPEGGIO_DOWN) if is_slash else (
                 P.STACCATO, P.MARCATO, P.SFORZANDO, P.FERMATA, P.PICK_DOWN,
                 P.PICK_UP, P.ARPEGGIO_UP, P.ARPEGGIO_DOWN)
        staccato, marcato, sfz, fermata, down, up, arp_up, arp_down = flags
        if src.has(staccato):
            ev.post.append("-.")
        if src.has(marcato):
            ev.post.append("->")
        if src.has(sfz):
            ev.post.append("-^")
        if fermata and src.has(fermata):
            ev.post.append("\\fermata")
        if src.has(down):
            ev.post.append("\\downbow")
        if src.has(up):
            ev.post.append("\\upbow")
        if src.has(arp_up) or src.has(arp_down):
            direction = "UP" if src.has(arp_up) else "DOWN"
            ev.pre.append(f"\\once \\override Arpeggio.arpeggio-direction = #{direction}")
            ev.post.append("\\arpeggio")

    def fill_slash(self, ev: Event, previous: Optional[Event]) -> None:
        s = ev.source
        assert isinstance(s, P.RhythmSlash)
        ev.beam_start, ev.beam_end = s.beam_start, s.beam_end
        if ev.rest:
            return
        note = NoteOut(71, 0, dead=s.has(P.SLASH_MUTED))   # b' sits on the middle line
        ev.notes.append(note)
        if s.has(P.SLASH_TIED) and previous is not None:
            previous.notes[0].tie = True
        if s.single_note:
            string, fret = s.single_note
            ev.post.append(f'\\fx "{fret} (string {string + 1})"')
        if s.has(P.SLASH_SLIDE_IN_BELOW) or s.has(P.SLASH_SLIDE_IN_ABOVE):
            ev.post.append('\\fx "sl."')
        if s.has(P.SLASH_SLIDE_OUT_DOWN):
            ev.post.append("\\bendAfter #-4")
        if s.has(P.SLASH_SLIDE_OUT_UP):
            ev.post.append("\\bendAfter #+4")
        self.position_articulations(ev, s)

    # -- effects spanning several notes -------------------------------------

    def voice_streams(self) -> List[List[Event]]:
        """Every voice's events across the whole score, in order."""
        streams = []
        for st in range(self.num_staves):
            for v in range(2):
                streams.append([ev for bar in self.bars for ev in bar.voices[st][v].events])
        streams.append([ev for bar in self.bars for ev in bar.slashes.events])
        return streams

    def apply_spanners(self) -> None:
        for stream in self.voice_streams():
            main = [e for e in stream if e.full_bar_rest is None and not e.grace]
            self.apply_glissandos(main)
            self.apply_slurs(main)
            self.apply_palm_mute(main)
            self.apply_let_ring(main)
            self.apply_vibrato(main)
            self.apply_swells(main)
            self.apply_harmonic_labels(main)
            self.apply_whammy(main)
            self.apply_ottava([e for e in stream if not e.grace])
        for bar in self.bars:
            for vb in [vb for staff in bar.voices for vb in staff] + [bar.slashes]:
                self.apply_beams(vb.events)

    @staticmethod
    def apply_glissandos(events: List[Event]) -> None:
        """A slide line needs a note right after it to slide to."""
        for k, ev in enumerate(events):
            if ev.glissando and k + 1 < len(events) and not events[k + 1].rest:
                ev.post.append("\\glissando")

    @staticmethod
    def apply_slurs(events: List[Event]) -> None:
        """Hammer-ons, pull-offs and legato slides slur into the next note."""
        start: Optional[Event] = None
        for ev in events:
            if start is not None:
                if ev.rest:
                    start.post.remove("(")
                    start = None
                elif not ev.slur:
                    ev.post.append(")")
                    start = None
                continue
            if ev.slur and not ev.rest:
                ev.post.append("(")
                start = ev
        if start is not None:
            start.post.remove("(")

    @staticmethod
    def runs(events: List[Event], key) -> List[Tuple[int, int]]:
        """(first, last) index of each run of consecutive notes where key(ev) is set."""
        out = []
        i = 0
        while i < len(events):
            if events[i].rest or not key(events[i]):
                i += 1
                continue
            j = i
            while j + 1 < len(events) and not events[j + 1].rest \
                    and key(events[j + 1]) == key(events[i]):
                j += 1
            out.append((i, j))
            i = j + 1
        return out

    def apply_palm_mute(self, events: List[Event]) -> None:
        for i, j in self.runs(events, lambda e: e.pm):
            if j > i:
                events[i].post.append("\\pmOn")
                events[j].post.append("\\pmOff")
            else:
                events[i].post.append("\\pm")

    def apply_harmonic_labels(self, events: List[Event]) -> None:
        """One "A.H. 8va" label at the start of each run of such notes."""
        for i, _ in self.runs(events, lambda e: e.harmonic_label):
            events[i].post.append(f"\\fx {ly_string(events[i].harmonic_label)}")

    def apply_whammy(self, events: List[Event]) -> None:
        """A graph for each whammy bar event, with "w/bar" on the first of a run.

        Within a run, an amount is only written when it changes.
        """
        for i, j in self.runs(events, lambda e: e.whammy is not None):
            for k in range(i, j + 1):
                shorthand, amount = events[k].whammy
                if k == i:
                    amount = ("w/bar " + amount).strip()
                elif events[k - 1].whammy == events[k].whammy:
                    amount = ""
                events[k].post.append(f"\\{shorthand} {ly_string(amount)}")

    def apply_let_ring(self, events: List[Event]) -> None:
        for i, _ in self.runs(events, lambda e: e.let_ring):
            events[i].post.append("\\letRing")

    def apply_vibrato(self, events: List[Event]) -> None:
        """A wavy line from the first vibrato note to the note after the last."""
        for i, j in self.runs(events, lambda e: e.vibrato):
            if j + 1 < len(events):
                stop = events[j + 1]
            elif j > i:
                stop = events[j]
            else:
                events[i].post.append('\\fx "vib."' if events[i].vibrato == 1 else '\\fx "wide vib."')
                continue
            events[i].post.append("\\vibOn" if events[i].vibrato == 1 else "\\wideVibOn")
            stop.post.insert(0, "\\vibOff")

    @staticmethod
    def apply_swells(events: List[Event]) -> None:
        for k, ev in enumerate(events):
            if ev.swell and k + 1 < len(events):
                ev.post.append("\\<" if ev.swell > 0 else "\\>")
                events[k + 1].post.insert(0, "\\!")

    @staticmethod
    def apply_ottava(events: List[Event]) -> None:
        current = 0
        for ev in events:
            level = 0 if ev.rest or ev.full_bar_rest is not None else ev.ottava
            if level != current:
                ev.pre.insert(0, f"\\ottava #{level}")
                current = level
        if current and events:
            events[-1].post.append("\\ottava #0")

    @staticmethod
    def apply_beams(events: List[Event]) -> None:
        """Beam notes the way the Power Tab file does."""
        main = [e for e in events if not e.grace and e.full_bar_rest is None]
        start = None
        for k, ev in enumerate(main):
            if ev.beam_start:
                start = k
            if ev.beam_end and start is not None:
                group = main[start:k + 1]
                notes = [e for e in group if not e.rest]
                beamable = all(int(e.duration.rstrip(".")) >= 8 for e in group)
                if len(notes) >= 2 and beamable:
                    notes[0].post.insert(0, "[")
                    notes[-1].post.insert(0, "]")
                start = None

    def apply_dynamics(self) -> None:
        by_key: Dict[Tuple[int, int], List[P.Dynamic]] = {}
        for d in self.score.dynamics:
            by_key.setdefault((d.system, d.staff), []).append(d)

        def attach(events: List[Event], position: int, level: str) -> None:
            target = next((e for e in events if e.position >= position and not e.grace), None)
            if target is None:
                target = events[-1]
            target.post = [x for x in target.post if x.lstrip("\\") not in DYNAMICS.values()]
            target.post.append("\\" + level)

        for bar in self.bars:
            for st_index, staff_voices in enumerate(bar.voices):
                for d in by_key.get((bar.system_index, st_index), []):
                    if not (bar.start_pos <= d.position < bar.end_pos):
                        continue
                    events = staff_voices[0].events or staff_voices[1].events
                    if DYNAMICS.get(d.staff_volume) and events:
                        attach(events, d.position, DYNAMICS[d.staff_volume])
            for d in self.score.dynamics:
                if d.system == bar.system_index and bar.start_pos <= d.position < bar.end_pos \
                        and DYNAMICS.get(d.slash_volume) and bar.slashes.events:
                    attach(bar.slashes.events, d.position, DYNAMICS[d.slash_volume])

    def apply_guitar_labels(self) -> None:
        """Label a staff with "Gtr. N" wherever a different guitar takes it over."""
        def label(guitars: List[int]) -> str:
            text = " & ".join(f"Gtr. {g + 1}" for g in guitars)
            return f"\\fx \\markup \\box {ly_string(text)}"

        def attach(staff_voices: List[VoiceBar], min_pos: int, text: str) -> None:
            for vb in staff_voices:
                for ev in vb.events:
                    if ev.position >= min_pos and not ev.grace:
                        ev.post.append(text)
                        return

        previous: Dict[int, List[int]] = {}
        seen = set()
        for bar in self.bars:
            si = bar.system_index
            for st_index, staff_voices in enumerate(bar.voices):
                if st_index >= len(self.staff_guitars[si]):
                    continue
                if (si, st_index) not in seen:
                    seen.add((si, st_index))
                    guitars = self.staff_guitars[si][st_index]
                    if st_index in previous and previous[st_index] != guitars:
                        attach(staff_voices, 0, label(guitars))
                    previous[st_index] = guitars
                for (gsys, gst, gpos), guitars in sorted(self.guitar_changes.items()):
                    if gsys == si and gst == st_index and bar.start_pos <= gpos < bar.end_pos:
                        attach(staff_voices, gpos, label(guitars))
                        previous[st_index] = guitars

    # -- rendering: notes ---------------------------------------------------

    def render_note(self, n: NoteOut) -> str:
        s = f"\\harm {ly_string(n.tab_text)} " if n.tab_text else ""
        if n.dead:
            s += "\\deadNote "
        if n.ghost:
            s += "\\parenthesize "
        s += pitch_name(n.pitch, self.flats)
        if n.tie:
            s += "~"
        if n.repeat_tie:
            s += "\\repeatTie"
        if n.harmonic:
            s += "\\harmonic"
        return s + f"\\{n.string}"

    def render_event(self, ev: Event, beat_value: int) -> str:
        tokens: List[str] = []
        if ev.tuplet_open:
            tokens.append(f"\\tuplet {ev.tuplet_open} {{")
        if ev.full_bar_rest is not None:
            markups = [x for x in ev.post if x.startswith("\\fx")]
            tokens += ev.pre + ["R" + length_str(ev.full_bar_rest, beat_value)] + markups
        elif ev.grace and ev.rest:
            pass                                    # a grace rest takes no time: drop it
        else:
            if ev.rest:
                body = "r" + ev.duration
            elif ev.slash and not ev.notes[0].string:
                body = ("\\deadNote " if ev.notes[0].dead else "") + "b'" + ev.duration
                if ev.notes[0].tie:
                    body += "~"
            else:
                body = "<" + " ".join(self.render_note(n) for n in ev.notes) + ">" + ev.duration
                if ev.harmonic_fret is not None:
                    body = f"\\harmonicByFret #{ev.harmonic_fret} {body}"
                if ev.slide_in:
                    notes = " ".join(f"{pitch_name(pitch, self.flats)}\\{string}"
                                     for pitch, string in ev.slide_in)
                    body = f"\\slideIn <{notes}>16\\glissando {body}"
            if ev.tremolo and ev.duration.rstrip(".") in ("1", "2", "4", "8"):
                body += ":32"
            posts = unique(ev.post)
            if ev.grace:
                posts = [x for x in posts if x not in GLUED]
                pre = [x for x in ev.pre if not x.startswith("\\ottava")]
                tokens += [x for x in ev.pre if x.startswith("\\ottava")]
                tokens.append(f"\\{ev.grace} {{ " + " ".join(pre + [body] + posts) + " }")
            else:
                # Beams and slurs are written straight after the note: <c\3>8[
                body += "".join(x for x in posts if x in GLUED)
                tokens += ev.pre + [body] + [x for x in posts if x not in GLUED]
        if ev.tuplet_close:
            tokens.append("}")
        return " ".join(tokens)

    def render_voice_bar(self, vb: VoiceBar, bar: Bar, voice_index: int,
                         voice_cmd: str = "") -> str:
        parts = [voice_cmd] if voice_cmd else []
        if not vb.events:
            filler = "R" if voice_index == 0 else "s"
            parts.append(filler + length_str(bar.length, bar.beat_value))
            return " ".join(parts)
        parts += [self.render_event(ev, bar.beat_value) for ev in vb.events]
        if not vb.is_full_rest and vb.length < bar.length:
            parts.append("s" + length_str(bar.length - vb.length, bar.beat_value))
        return " ".join(p for p in parts if p)

    def staff_music(self, st: int) -> str:
        two_voices = any(bar.voices[st][1].events for bar in self.bars)
        beams = [any(e.beam_start for bar in self.bars for e in bar.voices[st][v].events)
                 for v in range(2)]
        lines: List[List[str]] = [[], []]
        prev_setup = None
        stems = "\\voiceOne"          # what "\\" sets up for the first voice
        for bi, bar in enumerate(self.bars):
            system = self.score.systems[bar.system_index]
            comments = self.bar_comments(bi, bar)
            if st < len(system.staves):
                staff = system.staves[st]
                tuning, capo, _ = self.tuning_for(bar.system_index, st, staff.string_count)
                setup = (tuple(tuning), capo, staff.clef)
                if prev_setup is not None and setup != prev_setup:
                    lines[0].extend(self.setup_change(prev_setup, setup))
                    self.tagged_staves.add(st)
                prev_setup = setup
            for v in range(2 if two_voices else 1):
                lines[v].extend(comments)
                voice_cmd = ""
                if two_voices and v == 0:
                    # Stems go up only while the second voice has notes.
                    wanted = "\\voiceOne" if bar.voices[st][1].events else "\\oneVoice"
                    if wanted != stems:
                        voice_cmd = stems = wanted
                lines[v].append(self.render_voice_bar(bar.voices[st][v], bar, v, voice_cmd)
                                + f" | % bar {bi + 1}")
        heads = ["\\autoBeamOff" if beams[v] else "" for v in range(2)]
        if two_voices:
            v1 = "\n    ".join(([heads[0]] if heads[0] else []) + lines[0])
            v2 = "\n    ".join(([heads[1]] if heads[1] else []) + lines[1])
            return ("<<\n  % Voice 1 (stems up while voice 2 is playing)\n  {\n    " + v1
                    + "\n  }\n  \\\\\n  % Voice 2\n  {\n    " + v2 + "\n  }\n>>")
        body = "\n  ".join(([heads[0]] if heads[0] else []) + lines[0])
        return "{\n  " + body + "\n}"

    def slash_music(self) -> str:
        lines = ["\\improvisationOn  % slash note heads"]
        if any(e.beam_start for bar in self.bars for e in bar.slashes.events):
            lines.append("\\autoBeamOff")
        for bi, bar in enumerate(self.bars):
            lines.extend(self.bar_comments(bi, bar))
            vb = bar.slashes
            if vb.events:
                body = self.render_voice_bar(vb, bar, 1)
            else:
                body = "s" + length_str(bar.length, bar.beat_value)
            lines.append(body + f" | % bar {bi + 1}")
        return "{\n  " + "\n  ".join(lines) + "\n}"

    def bar_comments(self, bi: int, bar: Bar) -> List[str]:
        comments = []
        if bar.rehearsal is not None:
            letter = chr(bar.rehearsal.letter) if 32 <= bar.rehearsal.letter < 127 else "?"
            desc = bar.rehearsal.description.strip()
            comments.append(f"% --- Section {letter}{': ' + desc if desc else ''} ---")
        return comments

    def setup_change(self, old: tuple, new: tuple) -> List[str]:
        """Lines that switch a staff to another guitar's tuning or clef.

        Tags keep each change on its own staff: "tab" lines are removed from
        the notation staff and "notation" lines from the tab staff.
        """
        tuning, capo, clef = new
        lines = ["% A different guitar or tuning from here on."]
        if (old[0], old[1]) != (tuning, capo):
            notes = " ".join(pitch_name(n + capo, False) for n in reversed(tuning))
            restart = " \\stopStaff \\startStaff" if len(old[0]) != len(tuning) else ""
            lines.append(f"\\tag #'tab {{ \\set TabStaff.stringTunings = \\stringTuning <{notes}>"
                         f"{restart} }}")
        if old[2] != clef:
            lines.append(f"\\tag #'notation {{ \\clef \"{'bass_8' if clef == 1 else 'treble_8'}\" }}")
        return lines

    # -- rendering: global --------------------------------------------------

    def global_music(self) -> str:
        lines = []
        cur_time = cur_key = cur_length = None
        prev_closing: Optional[int] = None
        prev_system = -1
        for bi, bar in enumerate(self.bars):
            cmds = []
            notes = []
            bl = bar.start_barline
            if bar.system_index != prev_system:
                if self.options.keep_systems and prev_system >= 0:
                    lines.append("\\break")
                lines.append(f"% Power Tab line {bar.system_index + 1}")
                prev_system = bar.system_index
            # Bar line before this bar.
            if bl.type == P.Barline.REPEAT_START:
                glyph = ":|.|:" if prev_closing == P.Barline.REPEAT_END else ".|:"
                cmds.append(f'\\bar "{glyph}"')
            elif prev_closing is not None and prev_closing != P.Barline.BAR:
                cmds.append(f'\\bar "{BAR_GLYPHS.get(prev_closing, "|")}"')
            # Time signature.
            t = bl.time
            time = (t.beats, t.beat_value, t.common_time, t.cut_time)
            if time != cur_time:
                if not t.shown:
                    cmds.append("\\once \\omit Staff.TimeSignature")
                    notes.append("hidden time signature")
                if t.common_time:
                    cmds.append("\\defaultTimeSignature \\time 4/4")
                elif t.cut_time:
                    cmds.append("\\defaultTimeSignature \\time 2/2")
                else:
                    cmds.append(f"\\numericTimeSignature \\time {t.beats}/{t.beat_value}")
                cur_time = time
                cur_length = bar.nominal
            # Key signature.
            k = bl.key
            key = (k.fifths, k.minor)
            if key != cur_key:
                if cur_key is not None and not k.cancellation:
                    cmds.append("\\once \\omit Staff.KeyCancellation")
                if not k.shown and cur_key is not None:
                    cmds.append("\\once \\omit Staff.KeySignature")
                    notes.append("hidden key change")
                tonic = (MINOR_KEYS if key[1] else MAJOR_KEYS)[key[0] + 7]
                cmds.append(f"\\key {tonic} \\{'minor' if key[1] else 'major'}")
                cur_key = key
            # Bar length, when the bar doesn't match its time signature.
            target = bar.nominal if bar.multibar > 1 else bar.length
            if target != cur_length:
                cmds.append(f"\\set Timing.measureLength = #{target.numerator}/{target.denominator}")
                if target != bar.nominal:
                    notes.append("bar contents don't match the time signature")
                cur_length = target
            if bar.multibar > 1:
                notes.append(f"{bar.multibar} bars rest")
            if bi == 0 and self.starts_with_grace():
                # Lets the opening signatures come before the first grace note.
                cmds.append("\\grace { s8 }")
                notes.append("the music starts with a grace note")
            comment = f" % bar {bi + 1}" + (f" ({'; '.join(notes)})" if notes else "")
            lines.append(" ".join(cmds + ["s" + length_str(bar.length, bar.beat_value), "|"])
                         + comment)
            prev_closing = bar.closing_bar
        if prev_closing == P.Barline.REPEAT_END:
            lines.append('\\bar ":|."')
        elif prev_closing in (P.Barline.DOUBLE, P.Barline.FINE, P.Barline.FREETIME):
            lines.append(f'\\bar "{BAR_GLYPHS[prev_closing]}"')
        else:
            lines.append('\\bar "|."')
        return "{\n  " + "\n  ".join(lines) + "\n}"

    def starts_with_grace(self) -> bool:
        first = self.bars[0]
        voices = [vb for staff in first.voices for vb in staff] + [first.slashes]
        return any(vb.events and vb.events[0].grace for vb in voices)

    # -- rendering: marks ---------------------------------------------------

    def ending_commands(self) -> Dict[int, List[str]]:
        """Bar index -> repeatCommands entries for alternate endings.

        As in Power Tab, an ending runs to the next repeat-end bar line on the
        same line of music, or else just to the next bar line.
        """
        starts: Dict[int, List[str]] = {}       # bar index -> labels starting there
        for ae in self.score.alternate_endings:
            start = next((bi for bi, bar in enumerate(self.bars)
                          if bar.system_index == ae.system
                          and bar.start_pos <= ae.position < bar.end_pos), None)
            if start is None:
                continue
            labels = [f"{n}." for n in ae.numbers]
            labels += [txt for flag, txt in ((ae.da_capo, "D.C."), (ae.dal_segno, "D.S."),
                                             (ae.dal_segno_segno, "D.S.S.")) if flag]
            # Two endings starting in the same bar share one bracket.
            starts.setdefault(start, []).extend(labels or ["1."])
        cmds: Dict[int, List[str]] = {}
        ordered = sorted(starts)
        for k, start in enumerate(ordered):
            next_start = ordered[k + 1] if k + 1 < len(ordered) else len(self.bars)
            system = self.bars[start].system_index
            end = start
            for j in range(start, next_start):
                if self.bars[j].system_index != system:
                    break
                if self.bars[j].closing_bar == P.Barline.REPEAT_END:
                    end = j
                    break
            cmds.setdefault(start, []).append(
                f"(volta {ly_string(' '.join(unique(starts[start])))})")
            cmds.setdefault(end + 1, []).insert(0, "(volta #f)")
        return cmds

    def floating_texts(self) -> Dict[Tuple[int, int], List[str]]:
        """(system, position) -> texts, placed the way PTE 2.0 places them."""
        out: Dict[Tuple[int, int], List[str]] = {}
        systems = self.score.systems
        for ft in self.score.floating_texts:
            if not ft.text.strip() or not systems:
                continue
            si = next((i for i, s in enumerate(systems) if s.rect[3] > ft.rect[1]),
                      len(systems) - 1)
            pos = systems[si].position_from_x(ft.rect[0])
            out.setdefault((si, pos), []).append(ft.text)
        return out

    def marks_music(self) -> str:
        tempos: Dict[Tuple[int, int], List[P.TempoMarker]] = {}
        for t in self.score.tempo_markers:
            tempos.setdefault((t.system, t.position), []).append(t)
        endings = self.ending_commands()
        floating = self.floating_texts()
        lines = []
        for bi, bar in enumerate(self.bars):
            system = self.score.systems[bar.system_index]
            items: List[Tuple[Fraction, str, bool]] = []   # (offset, text, attach to spacer)

            def offset_of(pos: int) -> Fraction:
                if pos in bar.pos_offsets:
                    return bar.pos_offsets[pos]
                later = [o for p, o in bar.pos_offsets.items() if p > pos]
                return min(later) if later else bar.length    # after the last note

            def in_bar(pos: int) -> bool:
                return bar.start_pos <= pos < bar.end_pos

            if bi > 0:
                prev = self.bars[bi - 1]
                if prev.closing_bar == P.Barline.REPEAT_END and prev.closing_repeat_count > 2:
                    items.append((Fraction(0), f'\\textEndMark \\markup \\small '
                                  f'"x{prev.closing_repeat_count}"', False))
            if bi in endings:
                items.append((Fraction(0), "\\set Score.repeatCommands = "
                              f"#'({' '.join(endings[bi])})", False))
            if bar.rehearsal is not None:
                rs = bar.rehearsal
                letter = chr(rs.letter) if 32 <= rs.letter < 127 else "?"
                desc = f" {ly_string(rs.description)}" if rs.description.strip() else ""
                items.append((Fraction(0), f"\\mark \\markup {{ \\box \\bold {ly_string(letter)}{desc} }}",
                              False))
            for (tsys, tpos), markers in sorted(tempos.items()):
                if tsys == bar.system_index and in_bar(tpos):
                    for t in markers:
                        for cmd in self.tempo_commands(t):
                            items.append((offset_of(tpos), cmd, False))
            for d in system.directions:
                if in_bar(d.position):
                    for cmd in self.direction_commands(d):
                        items.append((offset_of(d.position), cmd, False))
            for ct in system.chord_texts:
                if in_bar(ct.position):
                    items.append((offset_of(ct.position), f"\\chord {ly_string(chord_text(ct.name))}",
                                  True))
            for (fsys, fpos), texts in sorted(floating.items()):
                if fsys == bar.system_index and in_bar(fpos):
                    lines_markup = " ".join(ly_string(t) for text in texts
                                            for t in text.replace("\r", "").split("\n") if t.strip())
                    items.append((offset_of(fpos), f"\\fx \\markup \\italic \\column {{ {lines_markup} }}", True))
            lines.append(self.spacer_line(bar, items) + f" | % bar {bi + 1}")
        last = self.bars[-1]
        if last.closing_bar == P.Barline.REPEAT_END and last.closing_repeat_count > 2:
            lines.append(f'\\textEndMark \\markup \\small "x{last.closing_repeat_count}"')
        if len(self.bars) in endings:
            lines.append(f"\\set Score.repeatCommands = #'({' '.join(endings[len(self.bars)])})")
        return "{\n  " + "\n  ".join(lines) + "\n}"

    @staticmethod
    def spacer_line(bar: Bar, items: List[Tuple[Fraction, str, bool]]) -> str:
        """Invisible spacers that put each mark at its time within the bar."""
        clamp = [(min(o, bar.length), t, a) for o, t, a in items]
        offsets = sorted({o for o, _, _ in clamp if o < bar.length} | {Fraction(0)})
        segments = []
        for k, o in enumerate(offsets):
            nxt = offsets[k + 1] if k + 1 < len(offsets) else bar.length
            here = [(t, a) for oo, t, a in clamp if oo == o or (oo >= bar.length and o == offsets[-1])]
            commands = [t for t, a in here if not a]
            # LilyPond takes one tempo change per moment and drops the rest
            # with a warning; keep the first, as it would.
            first = next((k for k, t in enumerate(commands) if "\\tempo " in t), None)
            commands = [t for k, t in enumerate(commands) if "\\tempo " not in t or k == first]
            attached = [t for t, a in here if a]
            segments.append(" ".join(commands + ["s" + length_str(nxt - o, bar.beat_value)] + attached))
        return " ".join(segments)

    @staticmethod
    def tempo_commands(t: P.TempoMarker) -> List[str]:
        desc = t.description.strip()
        beat = TEMPO_BEATS[t.beat_type] if t.beat_type < len(TEMPO_BEATS) else "4"
        text = f"{ly_string(desc)} " if desc else ""
        cmds = []
        if t.type == 1 and 0 < t.bpm < 1000:
            cmds.append(f"\\tempo {text}{beat} = {t.bpm}")
        elif t.type == 2:
            other = TEMPO_BEATS[t.listesso_beat_type] if t.listesso_beat_type < len(TEMPO_BEATS) else "4"
            cmds.append(f"\\tempo \\markup {{ \\rhythm {{ {beat} }} = \\rhythm {{ {other} }} }}")
        elif t.type == 3:
            cmds.append('\\textMark \\markup \\italic ' + ('"accel."' if t.beat_type == 0 else '"rit."'))
        elif 0 < t.bpm < 1000:
            # A hidden metronome mark: sets the speed without printing it.
            hidden = "\\set Score.tempoHideNote = ##t "
            cmds.append(f"{hidden}\\tempo {text}{beat} = {t.bpm} \\set Score.tempoHideNote = ##f")
        elif desc:
            cmds.append(f"\\tempo {ly_string(desc)}")
        if t.triplet_feel in TRIPLET_FEEL_TEXT:
            # e.g. "Triplet feel: two eighths = quarter + eighth triplet"
            unit, label = TRIPLET_FEEL_TEXT[t.triplet_feel]
            longer = int(unit) // 2
            cmds.append(f"\\textMark \\markup \\small \\line {{ {ly_string(label)} "
                        f"\\rhythm {{ {unit}[ {unit}] }} = "
                        f"\\rhythm {{ \\tuplet 3/2 {{ {longer} {unit} }} }} }}")
        return cmds

    @staticmethod
    def direction_commands(d: P.Direction) -> List[str]:
        cmds = []
        for sym, active, repeat in d.decoded():
            extra = []
            if active in DIRECTION_ACTIVE:
                extra.append(DIRECTION_ACTIVE[active])
            if repeat:
                extra.append(f"{ordinal(repeat)} time")
            suffix = f" ({', '.join(extra)})" if extra else ""
            if sym in DIRECTION_GLYPH:
                glyph = f"\\musicglyph {ly_string(DIRECTION_GLYPH[sym])}"
                if sym in (1, 3):           # double coda / segno segno: two glyphs
                    glyph = f"\\concat {{ {glyph} {glyph} }}"
                body = f"\\line {{ {glyph} {ly_string(suffix.strip())} }}" if suffix else glyph
                cmds.append(f"\\textMark \\markup {body}")
            elif sym in DIRECTION_TEXT:
                cmds.append(f"\\textMark \\markup \\italic {ly_string(DIRECTION_TEXT[sym] + suffix)}")
        return cmds

    # -- top level ----------------------------------------------------------

    def convert(self) -> Tuple[str, str, str]:
        """Return (variable definitions, layout score block, MIDI score block)."""
        self.assign_guitars()
        self.build_bars()
        if not self.bars:
            return "", "", ""
        self.flats = self.bars[0].start_barline.key.fifths < 0
        self.fill_notes()
        self.apply_spanners()
        self.apply_dynamics()
        self.apply_guitar_labels()

        p = self.prefix
        defs = [
            "% Time and key signatures, bar lines and bar lengths, shared by every staff.\n"
            f"{p}Global = {self.global_music()}\n",
            "% Tempo, section letters, repeat endings, directions and chord names.\n"
            f"{p}Marks = {self.marks_music()}\n",
        ]
        if self.has_slashes:
            defs.append(f"% Rhythm slashes (strum this rhythm with the chord shown).\n"
                        f"{p}Slashes = {self.slash_music()}\n")
        staves, midi_staves = [], []
        for st in range(self.num_staves):
            var = f"{p}Staff{ROMAN[st] if st < len(ROMAN) else st + 1}"
            staff, tuning, capo, offset, guitars = self.initial_staff_setup(st)
            names = " & ".join(f"Gtr. {g + 1}" for g in guitars) or f"Staff {st + 1}"
            desc = [f"Staff {st + 1} ({names})"]
            if offset:
                desc.append(f"notation shifted {offset:+d} semitones from the sounding pitch")
            defs.append(f"% {'; '.join(desc)}.\n{var} = {self.staff_music(st)}\n")
            staves.append(self.staff_block(st, var, staff, tuning, capo, offset, names))
            midi_staves.append(self.midi_staff(var, guitars, st == 0))
        slash_block = ""
        if self.has_slashes:
            slash_block = ("    \\new RhythmicStaff \\with { instrumentName = \"Rhythm\" } "
                           f"<< \\{p}Global \\{p}Slashes >>\n")
        score = ("\\score {\n  <<\n"
                 "    % Chord names, tempo and section marks on their own line, so they\n"
                 "    % stay visible when the top staff is hidden.\n"
                 f"    \\new Dynamics << \\{p}Global \\{p}Marks >>\n"
                 + slash_block + "".join(staves) + "  >>\n"
                 "  \\layout {\n"
                 "    \\context { \\Score \\compressEmptyMeasures" +
                 (" \\autoLineBreaksOff" if self.options.keep_systems else "") + " }\n"
                 "    % Spread notes so a short hairpin is still visible between\n"
                 "    % the dynamics at its ends.\n"
                 "    \\context { \\Score \\override Hairpin.minimum-length = #6 }\n"
                 "    % Hide staves that only have rests on a line of music.\n"
                 "    \\context { \\Staff \\RemoveAllEmptyStaves }\n"
                 "    \\context { \\TabStaff \\RemoveAllEmptyStaves }\n"
                 "    \\context { \\RhythmicStaff \\RemoveAllEmptyStaves }\n"
                 "  }\n}\n")
        midi = ""
        if self.options.midi:
            midi = ("% MIDI playback: notation staves only, repeats played once.\n"
                    "\\score {\n  <<\n" + "".join(midi_staves) + "  >>\n  \\midi { }\n}\n")
        return "\n".join(defs), score, midi

    def initial_staff_setup(self, st: int):
        for si, system in enumerate(self.score.systems):
            if st < len(system.staves):
                staff = system.staves[st]
                tuning, capo, offset = self.tuning_for(si, st, staff.string_count)
                return staff, tuning, capo, offset, self.guitars_on(si, st)
        return None, STANDARD_TUNINGS[6], 0, 0, []   # pragma: no cover - staff always exists

    def staff_block(self, st, var, staff, tuning, capo, offset, name) -> str:
        p = self.prefix
        clef = "bass_8" if staff is not None and staff.clef == 1 else "treble_8"
        tunings = " ".join(pitch_name(n + capo, False) for n in reversed(tuning))
        keep = " \\override VerticalAxisGroup.remove-empty = ##f" if st == 0 else ""
        notation, tab = f"\\{var}", f"\\{var}"
        if st in self.tagged_staves:
            notation = f"\\removeWithTag #'tab {notation}"
            tab = f"\\removeWithTag #'notation {tab}"
        if offset:
            # Written pitch = sounding pitch + offset (Power Tab's notation offset).
            notation = f"\\naturalizeMusic \\transpose c {pitch_name(48 + offset, offset < 0)} {notation}"
            self.transposed = True
        comment = "    % The first staff is never hidden, so no line of music is empty.\n" if st == 0 else ""
        return (comment +
                f"    \\new StaffGroup \\with {{ instrumentName = {ly_string(name)} }} <<\n"
                f"      \\new Staff \\with {{ \\omit StringNumber{keep} }}\n"
                f"        << \\clef \"{clef}\" \\{p}Global {notation} >>\n"
                f"      \\new TabStaff \\with {{ stringTunings = \\stringTuning <{tunings}>{keep} }}\n"
                f"        << \\{p}Global {tab} >>\n"
                f"    >>\n")

    def midi_staff(self, var: str, guitars: List[int], first: bool) -> str:
        g = self.guitar(guitars[0]) if guitars else None
        settings = []
        if g is not None:
            preset = g.preset if g.preset < len(GM_INSTRUMENTS) else 0
            settings = [f'midiInstrument = "{GM_INSTRUMENTS[preset]}"',
                        f"midiPanPosition = #{(min(g.pan, 127) - 64) / 64:.2f}",
                        f"midiReverbLevel = #{min(g.reverb, 127) / 127:.2f}",
                        f"midiChorusLevel = #{min(g.chorus, 127) / 127:.2f}",
                        f"midiMaximumVolume = #{min(g.volume, 127) / 127:.2f}"]
        marks = f" \\{self.prefix}Marks" if first else ""
        return (f"    \\new Staff \\with {{ {' '.join(settings)} }}\n"
                f"      << \\{self.prefix}Global{marks} \\{var} >>\n")


# ---------------------------------------------------------------------------
# Document level
# ---------------------------------------------------------------------------

def release_text(h: P.Header) -> str:
    title = h.release_title.strip()
    if h.release_type == 0 and title:
        kind = AUDIO_RELEASE[h.audio_type] if h.audio_type < len(AUDIO_RELEASE) else "album"
        text = f'From the {kind} "{title}"'
        if h.year:
            text += f" ({h.year})"
    elif h.release_type == 1 and title:
        text = f'From the video "{title}"'
    elif h.release_type == 2 and title:
        text = f'Bootleg "{title}"' + (f" ({h.year})" if h.year else "")
    else:
        return ""
    if h.live and h.release_type in (0, 1):
        text += ", live"
    return text


def header_block(h: P.Header) -> str:
    fields = []

    def add(name: str, value: str) -> None:
        if value and value.strip():
            fields.append(f"  {name} = {ly_string(value)}")

    add("title", h.title)
    if h.file_type == P.FILETYPE_SONG:
        add("subtitle", h.artist)
        add("subsubtitle", release_text(h))
        if h.author_type == 1:
            add("composer", "Traditional")
        else:
            add("composer", h.composer)
            add("poet", h.lyricist)
        if h.arranger.strip():
            add("arranger", "Arr. " + h.arranger)
        if h.guitar_transcriber.strip():
            add("opus", "Transcribed by " + h.guitar_transcriber)
    else:
        add("subtitle", h.subtitle)
        style = MUSIC_STYLES[h.music_style] if h.music_style < len(MUSIC_STYLES) else ""
        level = LESSON_LEVELS[h.level] if h.level < len(LESSON_LEVELS) else ""
        add("subsubtitle", " lesson, ".join(x for x in (style, level) if x)
            + (" level" if level else ""))
        add("composer", h.author)
    add("copyright", h.copyright)
    fields.append("  tagline = ##f")
    return "\\header {\n" + "\n".join(fields) + "\n}\n"


def text_markup(title: str, text: str) -> str:
    """A titled block of free text, one markup line per source line.

    A markup list rather than a single markup, so LilyPond can carry long
    text over onto the next page instead of squeezing it onto one.
    """
    lines = [l.rstrip() for l in text.replace("\r", "").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return ""
    body = "".join(f"  \\line {{ {ly_string(l) if l.strip() else '\" \"'} }}\n" for l in lines)
    return (f"% {title}: a markup list, so long text continues onto the next page.\n"
            f"\\markuplist \\column-lines {{\n  \\vspace #1\n  \\bold {ly_string(title)}\n"
            + body + "}\n")


def guitars_markup(score: P.Score) -> str:
    lines = []
    for g in score.guitars:
        bits = [f"Gtr. {g.number + 1}"]
        if any(c.isalnum() for c in g.description) and g.description.strip().lower() != "untitled":
            bits.append(g.description.strip())
        bits.append(tuning_text(g.tuning))
        if g.capo:
            bits.append(f"capo {g.capo}")
        lines.append(" — ".join(bits))
    if not lines:
        return ""
    return ("% The guitars in this score and their tunings.\n\\markup \\small \\column {\n"
            + "".join(f"  \\line {{ {ly_string(l)} }}\n" for l in lines) + "}\n")


def chord_diagrams_markup(score: P.Score) -> str:
    """Chord diagrams as fret-diagram markups (low string first)."""
    items = []
    for d in score.chord_diagrams:
        frets = ["x" if f >= 0xFE else ("o" if f == 0 else str(f)) for f in reversed(d.frets)]
        if not frets:
            continue
        details = ""
        if len(frets) != 6:
            details = f"\\override #'(fret-diagram-details . ((string-count . {len(frets)}))) "
        items.append(f"  \\center-column {{ {ly_string(chord_text(d.name))} "
                     f"{details}\\fret-diagram-terse \"{';'.join(frets)};\" }}\n")
    if not items:
        return ""
    return ("% Chord diagrams.\n\\markup \\column {\n  \\vspace #0.5\n  \\wordwrap {\n"
            + "".join("  " + i for i in items) + "  }\n}\n")


def convert_document(doc: P.Document, include_lyrics: bool = True,
                     options: Optional[Options] = None) -> str:
    options = options or Options(lyrics=include_lyrics)
    h = doc.header
    intro = [f'\\version "2.26.0"\n']
    origin = f' from "{options.source_name}"' if options.source_name else ""
    intro.append(f"% Converted{origin} by ptb2ly.\n%\n" + READING_GUIDE)
    intro.append(SHORTHANDS)
    intro.append("% Slightly smaller staves, so notation and tab fit well on a page.\n"
                 "#(set-global-staff-size 18)\n")
    intro.append("% When choosing page breaks, plan for extra room between lines of music.\n"
                 "% LilyPond underestimates tall stacks of marks above the staff, and\n"
                 "% would otherwise squeeze an over-full page. The printed spacing is\n"
                 "% unchanged (only padding differs from the defaults).\n"
                 "\\paper {\n"
                 "  page-breaking-system-system-spacing =\n"
                 "    #'((basic-distance . 12) (minimum-distance . 8) (padding . 6) (stretchability . 60))\n"
                 "}\n")
    intro.append(header_block(h))

    scores = [("guitar", doc.guitar_score, h.guitar_transcriber, h.guitar_notes, "Guitar"),
              ("bass", doc.bass_score, h.bass_transcriber, h.bass_notes, "Bass")]
    present = [s for s in scores if not s[1].is_empty]
    defs_out, blocks = [], []
    for prefix, score, transcriber, notes, title in present:
        # A score with notes always has at least one bar, so block is never empty.
        converter = ScoreConverter(score, prefix, options)
        defs, block, midi = converter.convert()
        if converter.transposed and NATURALIZE not in intro:
            intro.insert(intro.index(SHORTHANDS) + 1, NATURALIZE)
        banner = "%" * 70
        defs_out.append(f"{banner}\n% {title} score\n{banner}\n\n{defs}")
        if len(present) > 1:
            piece = [f"    piece = {ly_string(title)}"]
            if transcriber.strip():
                piece.append(f"    opus = {ly_string('Transcribed by ' + transcriber)}")
            block = block.replace("\\score {\n", "\\score {\n  \\header {\n" +
                                  "\n".join(piece) + "\n  }\n", 1)
        extra = guitars_markup(score) + chord_diagrams_markup(score)
        if notes.strip():
            extra += text_markup("Performance notes", notes)
        blocks.append(extra + block + midi)
    out = intro + defs_out + blocks
    if h.file_type == P.FILETYPE_LESSON and h.notes.strip():
        out.append(text_markup("Lesson notes", h.notes))
    if options.lyrics and h.lyrics.strip():
        out.append(text_markup("Lyrics", h.lyrics))
    return "\n".join(out)
