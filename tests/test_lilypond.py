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

"""Tests for the LilyPond converter, one Power Tab feature at a time."""

import re

import pytest

from ptb2ly import lilypond as L
from ptb2ly import ptbparser as P
from ptbbuilder import (BASS, barline, chord_name, chord_text, diagram, direction, dynamic,
                        ending, floating, guitar, guitar_in, note, one_bar, pos, rest, score,
                        slash, song, staff, system, tempo, to_bytes)

E6 = note(5, 0)          # open low E
A5 = note(4, 0)          # open A


def ly(doc: P.Document, **options) -> str:
    return L.convert_document(P.parse_bytes(to_bytes(doc)), options=L.Options(**options))


def block(text: str, name: str) -> str:
    """The body of a variable such as guitarStaffI."""
    match = re.search(rf"^{name} = (.*?)^(?=\S)", text + "\nEND", re.S | re.M)
    assert match, f"{name} not found"
    return match.group(1)


def staff1(doc: P.Document, **options) -> str:
    return block(ly(doc, **options), "guitarStaffI")


def marks(doc: P.Document) -> str:
    return block(ly(doc), "guitarMarks")


def global_(doc: P.Document) -> str:
    return block(ly(doc), "guitarGlobal")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_pitch_name():
    assert L.pitch_name(60, False) == "c'"
    assert L.pitch_name(40, False) == "e,"
    assert L.pitch_name(49, True) == "des"
    assert L.pitch_name(84, False) == "c'''"


def test_length_str():
    from fractions import Fraction as F
    assert L.length_str(F(3, 4), 4) == "4*3"
    assert L.length_str(F(2), 4) == "4*8"
    assert L.length_str(F(1, 3), 4) == "1*1/3"
    assert L.length_str(F(3), 3) == "3*9"
    assert L.length_str(F(7, 6), 4) == "1*7/6"


def test_length_str_whole_numbers():
    from fractions import Fraction as F
    assert L.length_str(F(2), 3) == "3*6"
    assert L.length_str(F(5, 1), 7) == "7*35"


def test_ly_string_escapes():
    assert L.ly_string('say "hi"\\ \n  now') == '"say \\"hi\\"\\\\ now"'


def test_ordinal():
    assert [L.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]


def test_quarter_steps():
    assert [L.quarter_steps(q) for q in (1, 2, 3, 4, 5, 6, 8)] == \
        ["¼", "½", "¾", "full", "1¼", "1½", "2"]


@pytest.mark.parametrize("bend, expected", [
    ((0, 4, 0, 0), '\\bendUp "full"'),
    ((0, 0, 0, 0), '\\bendUp "full"'),
    ((1, 2, 0, 0), '\\bendUp "½ & rel."'),
    ((2, 4, 0, 0), '\\bendUp "full & hold"'),
    ((3, 4, 0, 0), '\\bendUp "pre full"'),
    ((4, 4, 0, 0), '\\bendUp "pre full & rel."'),
    ((5, 6, 0, 0), '\\bendUp "pre 1½ & hold"'),
    ((6, 4, 2, 0), '\\bendDown "rel. ½"'),
    ((7, 4, 0, 0), '\\bendDown "rel."'),
    ((9, 4, 0, 0), '\\bendUp "full"'),
])
def test_bend_markup(bend, expected):
    assert L.bend_markup(bend) == expected


def test_volume_dynamic():
    assert L.volume_dynamic(127) == "fff"
    assert L.volume_dynamic(70) == "mf"
    assert L.volume_dynamic(5) == "ppp"


def test_chord_text_extras():
    assert L.chord_text(chord_name(9, 1)) == "Am"
    assert L.chord_text(chord_name(9, 1, extra=(1 << 5) | 6)) == "Am (V, type 2)"
    assert L.chord_text(chord_name(9, 1, extra=1)) == "Am"        # fret 0: no numeral


def test_tuning_text():
    from ptbbuilder import tuning
    assert L.tuning_text(tuning()) == "Standard (E A D G B E)"
    assert L.tuning_text(tuning([63, 58, 54, 49, 44, 39], name="", sharps=False)) == \
        "Tuning (Eb Ab Db Gb Bb Eb)"


def test_unique():
    assert L.unique(["a", "b", "a"]) == ["a", "b"]


# ---------------------------------------------------------------------------
# Header and text
# ---------------------------------------------------------------------------

def test_header_fields():
    text = ly(song(title="T", artist="A", composer="C", lyricist="L", arranger="Arr",
                   guitar_transcriber="Tr", copyright="(c) me"))
    for line in ('title = "T"', 'subtitle = "A"', 'composer = "C"', 'poet = "L"',
                 'arranger = "Arr. Arr"', 'opus = "Transcribed by Tr"',
                 'copyright = "(c) me"', "tagline = ##f"):
        assert line in text


def test_traditional_song():
    assert 'composer = "Traditional"' in ly(song(author_type=1))


@pytest.mark.parametrize("fields, expected", [
    (dict(release_type=0, release_title="LP", year=1999, audio_type=2), 'From the album \\"LP\\" (1999)'),
    (dict(release_type=0, release_title="S", audio_type=0, live=True), 'From the single \\"S\\", live'),
    (dict(release_type=0, release_title="X", audio_type=9), 'From the album \\"X\\"'),
    (dict(release_type=1, release_title="V", live=True), 'From the video \\"V\\", live'),
    (dict(release_type=2, release_title="B", year=1970), 'Bootleg \\"B\\" (1970)'),
    (dict(release_type=2, release_title="B"), 'Bootleg \\"B\\"'),
])
def test_release_info(fields, expected):
    assert f'subsubtitle = "{expected}"' in ly(song(**fields))


def test_no_release_info():
    assert "subsubtitle" not in ly(song(release_type=0, release_title=""))
    assert L.release_text(song(release_type=3).header) == ""


def test_lesson():
    text = ly(song(file_type=P.FILETYPE_LESSON, title="Scales", subtitle="Part 1",
                   music_style=2, level=0, author="Teacher", notes="Go slowly"))
    assert 'subsubtitle = "Blues lesson, Beginner level"' in text
    assert 'composer = "Teacher"' in text
    assert '"Lesson notes"' in text and '"Go slowly"' in text


def test_lesson_with_unknown_style_and_level():
    text = ly(song(file_type=P.FILETYPE_LESSON, music_style=99, level=9))
    assert "subsubtitle" not in text


def test_lyrics_and_options():
    doc = song(score([system([staff([rest(0)])])]), lyrics="Line one\r\n\r\nLine two\r\n\r\n")
    text = ly(doc)
    assert '"Lyrics"' in text and '"Line one"' in text and '"Line two"' in text
    assert '\\line { " " }' in text           # blank line kept
    # A markup list, so long lyrics can run onto the next page.
    assert '\\markuplist \\column-lines {\n  \\vspace #1\n  \\bold "Lyrics"\n' in text
    assert '"Lyrics"' not in ly(doc, lyrics=False)
    assert L.text_markup("x", "\n\n") == ""


def test_source_name_and_reading_guide():
    text = ly(song(), source_name="tune.ptb")
    assert '% Converted from "tune.ptb" by ptb2ly.' in text
    assert "How to read the music below" in text
    assert "pmOn = " in text


def test_default_options():
    doc = P.parse_bytes(to_bytes(song(lyrics="words")))
    assert '"Lyrics"' in L.convert_document(doc)
    assert '"Lyrics"' not in L.convert_document(doc, include_lyrics=False)


def test_empty_song_has_no_score():
    text = ly(song())
    assert "\\score" not in text


def test_score_with_no_bars():
    # Systems with no staves still produce bars; a score with no systems is empty.
    conv = L.ScoreConverter(score(), "guitar", L.Options())
    assert conv.convert() == ("", "", "")


# ---------------------------------------------------------------------------
# Notes and rhythm
# ---------------------------------------------------------------------------

def test_notes_and_strings():
    body = staff1(one_bar(pos(0, 4, notes=[E6]), pos(1, 8, P.DOTTED, notes=[note(3, 2)]),
                          pos(2, 16, notes=[note(1, 1), note(0, 0)]), pos(3, 2, notes=[A5])))
    assert "<e,\\6>4 <e\\4>8. <c'\\2 e'\\1>16 <a,\\5>2" in body


def test_capo_raises_pitch_but_not_tab_fret():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])])], guitars=[guitar(capo=2)]))
    text = ly(doc)
    assert "<fis,\\6>1" in text
    assert "\\stringTuning <fis, b, e a cis' fis'>" in text
    assert "capo 2" in text


def test_flat_keys_spell_with_flats():
    doc = one_bar(pos(0, 1, notes=[note(5, 1)]), start=barline(fifths=-2))
    assert "<f,\\6>1" in staff1(doc)
    doc = one_bar(pos(0, 1, notes=[note(5, 6)]), start=barline(fifths=-2))
    assert "<bes,\\6>1" in staff1(doc)


def test_rests():
    body = staff1(one_bar(pos(0, 2, notes=[E6]), rest(1, 2)))
    assert "<e,\\6>2 r2 | % bar 1" in body


def test_whole_bar_rest_fills_the_bar():
    body = staff1(one_bar(rest(0, 1), start=barline(beats=3, value=4)))
    assert "R4*3 | % bar 1" in body


def test_empty_bar_gets_a_bar_rest():
    doc = one_bar(pos(0, 1, notes=[E6]), barlines=[barline(2)])
    doc.guitar_score.systems[0].staves[0].voices[0].append(pos(3, 1))  # rest in bar 2
    assert "R4*4 | % bar 2" in staff1(doc)


def test_multibar_rest():
    doc = one_bar(pos(0, 1, complex=[(ord("j") << 24) | 4]))      # 4-bar rest
    body = staff1(doc)
    g = global_(doc)
    assert "R4*16 | % bar 1" in body
    assert "4 bars rest" in g and "s4*16" in g


def test_grace_notes():
    body = staff1(one_bar(pos(0, 8, P.ACCIACCATURA, notes=[note(2, 2)]),
                          pos(1, 1, notes=[note(2, 4)]),
                          pos(2, 8, P.APPOGGIATURA, notes=[note(2, 2)]),
                          pos(3, 8, P.ACCIACCATURA)))
    assert "\\acciaccatura { <a\\3>8 } <b\\3>1" in body
    assert "\\appoggiatura { <a\\3>8 }" in body


def test_grace_note_at_the_start():
    doc = one_bar(pos(0, 8, P.ACCIACCATURA, notes=[note(2, 2)]), pos(1, 1, notes=[note(2, 4)]))
    assert "\\key c \\major \\grace { s8 } s4*4" in global_(doc)
    assert "\\grace" not in global_(one_bar(pos(0, 1, notes=[note(2, 4)])))


def test_tuplets():
    t = P.GROUP_START
    body = staff1(one_bar(
        pos(0, 8, t, notes=[E6], beaming=(2 << 3) | 1),
        pos(1, 8, P.GROUP_MIDDLE, notes=[E6]),
        pos(2, 8, P.GROUP_END, notes=[E6]),
        pos(3, 8, t, notes=[E6], beaming=(2 << 3) | 1),      # restarted before ending
        pos(4, 8, t, notes=[E6], beaming=(2 << 3) | 1),
        pos(5, 8, P.GROUP_END, notes=[E6]),
        pos(6, 8, t, notes=[E6], beaming=0),                 # 1:1 is no tuplet
        pos(7, 4, t, notes=[E6], beaming=(2 << 3) | 1),      # left open at bar end
    ))
    assert "\\tuplet 3/2 { <e,\\6>8 <e,\\6>8 <e,\\6>8 }" in body
    assert "\\tuplet 3/2 { <e,\\6>8 } \\tuplet 3/2 { <e,\\6>8 <e,\\6>8 }" in body
    assert body.count("\\tuplet") == 4
    assert body.count("{") == body.count("}") + 1      # + the variable's own brace


def test_tuplet_with_grace_note_inside():
    body = staff1(one_bar(pos(0, 8, P.GROUP_START | P.ACCIACCATURA, notes=[E6],
                              beaming=(2 << 3) | 1),
                          pos(1, 8, P.GROUP_END, notes=[E6])))
    assert "\\tuplet 3/2 { \\acciaccatura { <e,\\6>8 } <e,\\6>8 }" in body


def test_grace_rest_inside_tuplet_keeps_braces():
    body = staff1(one_bar(pos(0, 8, P.GROUP_START | P.ACCIACCATURA, beaming=(2 << 3) | 1),
                          pos(1, 8, P.GROUP_END, notes=[E6])))
    assert "\\tuplet 3/2 { <e,\\6>8 }" in body


def test_unknown_duration_is_treated_as_quarter():
    item = L.TimedItem(0, 3, 0, False, None, None, False, None)
    bar = L.Bar(0, 0, 1, barline(), 0, 0, L.Fraction(1))
    assert L.ScoreConverter.time_events([item], bar).events[0].duration == "4"


def test_short_and_long_bars_keep_staves_in_step():
    doc = song(score([system([staff([pos(0, 4, notes=[E6]), pos(1, 4, notes=[E6]),
                                     pos(2, 4, notes=[E6])]),
                              staff([pos(0, 2, notes=[E6])])])],
                     guitar_ins=[guitar_in(0, 0, 0), guitar_in(0, 1, 0)]))
    text = ly(doc)
    assert "\\set Timing.measureLength = #3/4" in block(text, "guitarGlobal")
    assert "<e,\\6>2 s4*1" in block(text, "guitarStaffII")


def test_two_voices():
    doc = one_bar(pos(0, 1, notes=[note(0, 0)]), barlines=[barline(2)])
    st = doc.guitar_score.systems[0].staves[0]
    st.voices[0].append(pos(3, 1, notes=[note(0, 1)]))
    st.voices[1] = [pos(0, 1, notes=[E6])]
    body = staff1(doc)
    assert "% Voice 1" in body and "\\\\" in body and "% Voice 2" in body
    assert "\\oneVoice <f'\\1>1" in body           # voice 2 silent in bar 2
    assert "s4*4 | % bar 2" in body
    assert body.count("\\oneVoice") == 1


def test_missing_staff_in_a_system_is_filled_with_rests():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])]), staff([pos(0, 1, notes=[E6])])]),
                      system([staff([pos(0, 1, notes=[E6])])])],
                     guitar_ins=[guitar_in(0, 0, 0), guitar_in(0, 1, 0)]))
    assert "R4*4 | % bar 2" in block(ly(doc), "guitarStaffII")


def test_notes_on_strings_the_tuning_lacks_are_dropped():
    doc = song(score([system([staff([pos(0, 1, notes=[note(5, 0)])], strings=4)])],
                     guitars=[guitar(notes=BASS)]))
    body = staff1(doc)
    assert "r1" in body


# ---------------------------------------------------------------------------
# Ties, slurs, slides
# ---------------------------------------------------------------------------

def test_ties():
    body = staff1(one_bar(pos(0, 2, notes=[note(1, 0), note(0, 0)]),
                          pos(1, 2, notes=[note(1, 0, P.TIED), note(0, 0, P.TIED)])))
    assert "<b~\\2 e'~\\1>2 <b\\2 e'\\1>2" in body


def test_tie_after_a_rest_becomes_a_repeat_tie():
    body = staff1(one_bar(rest(0, 2), pos(1, 2, notes=[note(0, 0, P.TIED)])))
    assert "<e'\\repeatTie\\1>2" in body


def test_tie_across_padding_becomes_a_repeat_tie():
    doc = song(score([system([staff([pos(0, 2, notes=[E6]), pos(2, 1, notes=[note(5, 0, P.TIED)])]),
                              staff([pos(0, 1, notes=[E6]), pos(2, 1, notes=[E6])])],
                             barlines=[barline(1)])],
                     guitar_ins=[guitar_in(0, 0, 0), guitar_in(0, 1, 0)]))
    assert "<e,\\repeatTie\\6>1" in staff1(doc)


def test_tie_after_full_bar_rest():
    doc = one_bar(rest(0, 1), pos(2, 1, notes=[note(0, 0, P.TIED)]), barlines=[barline(1)])
    assert "\\repeatTie" in staff1(doc)


def test_grace_note_ties_are_ignored():
    body = staff1(one_bar(pos(0, 2, notes=[note(0, 0)]),
                          pos(1, 8, P.ACCIACCATURA, notes=[note(0, 0, P.TIED)]),
                          pos(2, 2, notes=[note(0, 1)])))
    assert "~" not in body


def test_hammer_on_and_pull_off_slurs():
    body = staff1(one_bar(pos(0, 4, notes=[note(2, 2, P.HAMMER_ON)]),
                          pos(1, 4, notes=[note(2, 4, P.PULL_OFF)]),
                          pos(2, 4, notes=[note(2, 2)]),
                          pos(3, 4, notes=[note(2, 2, P.HAMMER_ON)])))     # nothing to slur to
    assert "<a\\3>4( <b\\3>4 <a\\3>4)" in body
    assert body.count("(") == 1


def test_slur_into_a_rest_is_dropped():
    body = staff1(one_bar(pos(0, 4, notes=[note(2, 2, P.HAMMER_ON)]), rest(1, 4)))
    assert "(" not in body


def test_hammer_from_nowhere():
    body = staff1(one_bar(pos(0, 2, notes=[note(2, 2, P.HAMMER_ON | P.HAMMER_PULL_NOWHERE)]),
                          pos(1, 2, notes=[note(2, 2, P.PULL_OFF | P.HAMMER_PULL_NOWHERE)])))
    assert '\\fx "H"' in body and '\\fx "P"' in body and "(" not in body


def slide(into=0, out=0):
    return (ord("d") << 24) | (into << 16) | (out << 8)


def test_slides_between_notes():
    body = staff1(one_bar(pos(0, 4, notes=[note(2, 2, complex=[slide(out=1)])]),
                          pos(1, 4, notes=[note(2, 4, complex=[slide(out=2)])]),
                          pos(2, 4, notes=[note(2, 7)]),
                          pos(3, 4, notes=[note(2, 7, complex=[slide(out=1)])])))   # last note
    assert "<a\\3>4 \\glissando <b\\3>4( \\glissando <d'\\3>4)" in body
    assert body.count("\\glissando") == 2


def test_slides_off_a_note():
    body = staff1(one_bar(pos(0, 2, notes=[note(2, 5, complex=[slide(out=3)])]),
                          pos(1, 2, notes=[note(2, 5, complex=[slide(out=4)])])))
    assert "\\bendAfter #-4" in body and "\\bendAfter #+4" in body


def test_slides_into_a_note():
    body = staff1(one_bar(pos(0, 2, notes=[note(2, 5, complex=[slide(into=1)])]),
                          pos(1, 2, notes=[note(2, 5, complex=[slide(into=2)])]),
                          ))
    # From two frets below (fret 3) and two frets above (fret 7).
    assert "\\slideIn <ais\\3>16\\glissando <c'\\3>2" in body
    assert "\\slideIn <d'\\3>16\\glissando <c'\\3>2" in body


def test_slide_into_from_below_an_open_string_is_skipped():
    body = staff1(one_bar(pos(0, 1, notes=[note(2, 1, complex=[slide(into=5)])])))
    assert "\\slideIn" not in body


# ---------------------------------------------------------------------------
# Note and position effects
# ---------------------------------------------------------------------------

def test_dead_and_ghost_notes():
    body = staff1(one_bar(pos(0, 1, notes=[note(0, 0, P.MUTED), note(1, 0, P.GHOST)])))
    assert "<\\parenthesize b\\2 \\deadNote e'\\1>1" in body


def test_natural_harmonics():
    body = staff1(one_bar(pos(0, 2, notes=[note(5, 12, P.NATURAL_HARMONIC),
                                           note(4, 12, P.NATURAL_HARMONIC)]),
                          pos(1, 2, notes=[note(5, 12, P.NATURAL_HARMONIC), note(4, 7)])))
    assert "\\harmonicByFret #12 <e,\\6 a,\\5>2" in body
    assert "<e\\harmonic\\6 e\\5>2" in body


def test_note_labels():
    complexes = [
        (ord("e") << 24) | (4 << 4),                   # bend full
        (ord("g") << 24) | (7 << 16),                  # trill to fret 7
        (ord("f") << 24) | 17,                         # tapped harmonic at 17
    ]
    body = staff1(one_bar(pos(0, 2, notes=[note(2, 5, complex=complexes)]),
                          pos(1, 2, notes=[note(2, 5, complex=[(ord("h") << 24) | (1 << 16) | (1 << 8) | 0])]),
                          ))
    assert '\\bendUp "full"' in body and '\\trillTo "7"' in body
    # Fret 5 on the G string (c'), tapped 12 frets up / an octave harmonic of C.
    assert body.count('<\\harm "5(17)" c\'\\3>2') == 2
    assert '\\fx "T.H. 8va"' in body and '\\fx "A.H. 8va"' in body


def artificial(key: int, octave: int) -> int:
    return (ord("h") << 24) | (octave << 16) | (1 << 8) | key


def test_artificial_harmonics():
    # Written as the harmonic's note at or above the fretted c'; the tab shows
    # where it is touched when that is a usual harmonic.
    body = staff1(one_bar(pos(0, 4, notes=[note(2, 5, complex=[artificial(7, 1)])]),    # G 8va
                          pos(1, 4, notes=[note(2, 5, complex=[artificial(9, 2)])]),    # A 15ma
                          pos(2, 4, notes=[note(2, 5, complex=[artificial(9, 0)])]),    # A loco
                          pos(3, 4, notes=[note(2, 5, complex=[artificial(9, 0)])])))
    assert '<\\harm "5(12)" g\'\\3>4 \\fx "A.H. 8va"' in body
    assert '<\\harm "5" a\'\\3>4 \\fx "A.H. 15ma"' in body
    # One label for a run of notes with the same label.
    assert body.count('\\fx "A.H."') == 1


def test_tapped_harmonic_off_the_octave():
    body = staff1(one_bar(pos(0, 1, notes=[note(2, 5, complex=[(ord("f") << 24) | 12])])))
    assert '<\\harm "5(12)" c\'\\3>1 \\fx "T.H."' in body


@pytest.mark.parametrize("flag, expected", [
    (P.STACCATO, "-."), (P.MARCATO, "->"), (P.SFORZANDO, "-^"), (P.FERMATA, "\\fermata"),
    (P.PICK_DOWN, "\\downbow"), (P.PICK_UP, "\\upbow"), (P.TAP, '\\fx "T"'),
])
def test_articulations(flag, expected):
    assert expected in staff1(one_bar(pos(0, 1, flag, notes=[E6])))


def test_arpeggios():
    up = staff1(one_bar(pos(0, 1, P.ARPEGGIO_UP, notes=[E6, A5])))
    down = staff1(one_bar(pos(0, 1, P.ARPEGGIO_DOWN, notes=[E6, A5])))
    assert "\\once \\override Arpeggio.arpeggio-direction = #UP" in up and "\\arpeggio" in up
    assert "#DOWN" in down


def test_tremolo_picking():
    body = staff1(one_bar(pos(0, 2, P.TREMOLO_PICKING, notes=[E6]),
                          pos(1, 32, P.TREMOLO_PICKING, notes=[E6])))
    assert "<e,\\6>2:32" in body and "<e,\\6>32 " in body


def test_tremolo_bar():
    def whammy(ttype: int, pitch: int) -> int:
        return (ord("c") << 24) | (ttype << 16) | pitch

    # Every type in a row (a run), a rest, then one more and an unknown type.
    # The repeated dip at the end of the run doesn't repeat its amount.
    run = [(0, 2), (1, 4), (2, 6), (3, 0), (4, 0), (5, 1), (6, 2), (6, 2)]
    positions = [pos(i, 16, notes=[E6], complex=[whammy(t, q)]) for i, (t, q) in enumerate(run)]
    positions += [pos(8, 16, P.REST), pos(9, 16, notes=[E6], complex=[whammy(0, 8)]),
                  pos(10, 16, notes=[E6], complex=[whammy(9, 0)])]
    body = staff1(one_bar(*positions))
    for expected in ['\\wDip "w/bar −½"', '\\wDive "−1"', '\\wDiveHold "−1½"', '\\wRelease ""',
                     '\\wReturn ""', '\\wReturnHold "¼"', '\\wInvDip "+½" <e,\\6>16 \\wInvDip ""',
                     '\\wDip "w/bar −2"', '\\fx "w/bar"']:
        assert expected in body


def test_volume_swells():
    body = staff1(one_bar(pos(0, 4, notes=[E6], complex=[(ord("a") << 24) | (13 << 16) | (91 << 8)]),
                          pos(1, 4, notes=[E6], complex=[(ord("a") << 24) | (91 << 16) | (13 << 8)]),
                          pos(2, 2, notes=[E6], complex=[(ord("a") << 24) | (13 << 16) | (91 << 8)])))
    assert "<e,\\6>4 \\< <e,\\6>4 \\! \\> <e,\\6>2 \\!" in body


def test_hairpins_have_room():
    assert "\\override Hairpin.minimum-length = #6" in ly(one_bar(pos(0, 1, notes=[E6])))


def test_octave_signs():
    body = staff1(one_bar(pos(0, 4, notes=[note(0, 0, P.OCTAVE_8VA)]),
                          pos(1, 4, notes=[note(0, 0, P.OCTAVE_15MA)]),
                          pos(2, 4, notes=[note(0, 0, P.OCTAVE_8VB)]),
                          pos(3, 4, notes=[note(0, 0, P.OCTAVE_15MB)]),
                          ))
    assert "\\ottava #1 <e'\\1>4 \\ottava #2" in body
    assert "\\ottava #-1" in body and "\\ottava #-2" in body and "\\ottava #0" in body


def test_octave_sign_ends_at_rest():
    body = staff1(one_bar(pos(0, 2, notes=[note(0, 0, P.OCTAVE_8VA)]), rest(1, 2)))
    assert "\\ottava #0 r2" in body


def test_octave_sign_on_grace_note_stays_outside_the_grace():
    body = staff1(one_bar(pos(0, 8, P.ACCIACCATURA, notes=[note(0, 0, P.OCTAVE_8VA)]),
                          pos(1, 1, notes=[note(0, 0, P.OCTAVE_8VA)])))
    assert "\\ottava #1 <e'\\1>1" in body


def test_palm_muting():
    body = staff1(one_bar(pos(0, 8, P.PALM_MUTE, notes=[E6]), pos(1, 8, P.PALM_MUTE, notes=[E6]),
                          pos(2, 4, notes=[E6]), pos(3, 2, P.PALM_MUTE, notes=[E6])))
    assert "<e,\\6>8 \\pmOn <e,\\6>8 \\pmOff <e,\\6>4 <e,\\6>2 \\pm" in body


def test_let_ring():
    body = staff1(one_bar(pos(0, 2, P.LET_RING, notes=[E6]), pos(1, 2, P.LET_RING, notes=[E6])))
    assert body.count("\\letRing") == 1


def test_vibrato():
    body = staff1(one_bar(pos(0, 4, P.VIBRATO, notes=[E6]), pos(1, 4, P.VIBRATO, notes=[E6]),
                          pos(2, 4, notes=[E6]), pos(3, 4, P.WIDE_VIBRATO, notes=[E6])))
    assert "<e,\\6>4 \\vibOn <e,\\6>4 <e,\\6>4 \\vibOff" in body
    assert '\\fx "wide vib."' in body           # last note: nothing to stop on


def test_vibrato_run_at_the_end():
    body = staff1(one_bar(pos(0, 2, P.WIDE_VIBRATO, notes=[E6]), pos(1, 2, P.WIDE_VIBRATO, notes=[E6])))
    assert "<e,\\6>2 \\wideVibOn <e,\\6>2 \\vibOff" in body
    body = staff1(one_bar(pos(0, 1, P.VIBRATO, notes=[E6])))
    assert '\\fx "vib."' in body


def test_beams_from_the_file():
    s, e = 0x400, 0x2000
    body = staff1(one_bar(pos(0, 8, notes=[E6], beaming=s), pos(1, 8, notes=[E6]),
                          pos(2, 8, notes=[E6], beaming=e),
                          pos(3, 8, notes=[E6], beaming=s), pos(4, 4, notes=[E6], beaming=e),
                          pos(5, 8, notes=[E6], beaming=s), pos(6, 8, beaming=e)))
    assert "\\autoBeamOff" in body
    assert "<e,\\6>8[ <e,\\6>8 <e,\\6>8]" in body
    assert body.count("[") == 1                      # a quarter or a lone note isn't beamed


def test_no_beam_data_leaves_automatic_beaming():
    assert "\\autoBeamOff" not in staff1(one_bar(pos(0, 1, notes=[E6])))


# ---------------------------------------------------------------------------
# Dynamics and guitars
# ---------------------------------------------------------------------------

def test_dynamics():
    doc = song(score([system([staff([pos(0, 2, notes=[E6]), pos(2, 2, notes=[E6])])])],
                     dynamics=[dynamic(0, 0, 0, staff_volume=78), dynamic(0, 0, 0, staff_volume=39),
                               dynamic(0, 0, 1, staff_volume=104), dynamic(0, 0, 9, staff_volume=13),
                               dynamic(0, 0, 0, staff_volume=0xFF), dynamic(0, 5, 0, staff_volume=78)]))
    body = staff1(doc)
    # The later of two dynamics wins; one between notes goes on the next note;
    # unset volumes, other staves and positions outside the bar are ignored.
    assert "<e,\\6>2 \\p <e,\\6>2 \\fff" in body


def test_dynamics_go_to_voice_two_when_voice_one_is_empty():
    doc = song(score([system([staff([], [pos(0, 1, notes=[E6])])])],
                     dynamics=[dynamic(0, 0, 0, staff_volume=65)]))
    assert "\\mf" in staff1(doc)


def test_guitar_changes():
    doc = song(score(
        [system([staff([pos(0, 1, notes=[E6])])]),
         system([staff([pos(0, 2, notes=[E6]), pos(1, 2, notes=[E6])])]),
         system([staff([pos(0, 1, notes=[E6])])])],
        guitars=[guitar(0), guitar(1, notes=[62, 57, 53, 48, 43, 38], description="-")],
        guitar_ins=[guitar_in(0, 0, 0, [0]), guitar_in(1, 0, 0, [1]), guitar_in(1, 0, 1, [0, 1]),
                    guitar_in(2, 0, 0, [], slash_guitars=[0])]))
    text = ly(doc)
    body = block(text, "guitarStaffI")
    assert '\\fx \\markup \\box "Gtr. 2"' in body
    assert '\\fx \\markup \\box "Gtr. 1 & Gtr. 2"' in body
    assert "% A different guitar or tuning from here on." in body
    assert "\\set TabStaff.stringTunings = \\stringTuning <d, g, c f a d'>" in body
    assert "Gtr. 2 — Standard (D G C F A D)" in text      # "-" isn't a real description


def test_staff_without_guitar_in_uses_matching_guitar():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])]), staff([pos(0, 1, notes=[E6])], strings=4)])],
                     guitars=[guitar(0), guitar(1, notes=BASS)], guitar_ins=[]))
    text = ly(doc)
    assert 'instrumentName = "Gtr. 2"' in text
    assert "\\stringTuning <e,, a,, d, g,>" in text


def test_fallback_tunings():
    conv = L.ScoreConverter(score([system([staff([rest(0)], strings=7)])],
                                  guitars=[guitar(notes=BASS)]), "g", L.Options())
    conv.assign_guitars()
    assert conv.tuning_for(0, 0, 7) == (L.STANDARD_TUNINGS[7], 0, 0)
    assert conv.tuning_for(0, 0, 3)[0] == BASS[:3]
    conv = L.ScoreConverter(score([system([staff([rest(0)])])], guitars=[]), "g", L.Options())
    conv.assign_guitars()
    assert conv.guitar(0) is None
    assert conv.tuning_for(0, 0, 6)[0] == L.STANDARD_TUNINGS[6]
    assert conv.guitars_on(0, 5) == [0]


def test_unknown_guitar_number_falls_back_to_first():
    conv = L.ScoreConverter(score([system([staff([rest(0)])])]), "g", L.Options())
    assert conv.guitar(7).number == 0


def test_notation_offset_transposes_the_notation_only():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])])], guitars=[guitar(offset=-2)]))
    text = ly(doc)
    assert "\\transpose c bes, \\guitarStaffI" in text
    assert "notation shifted -2 semitones" in text
    assert "<< \\guitarGlobal \\guitarStaffI >>" in text      # tab unchanged


def test_bass_clef_and_bass_score():
    bass = score([system([staff([pos(0, 1, notes=[note(3, 0)])], strings=4, clef=1)])],
                 guitars=[guitar(notes=BASS, description="Bass")])
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])])]), bass,
               bass_transcriber="Bob", bass_notes="Use a pick")
    text = ly(doc)
    assert '\\clef "bass_8"' in text and "bassStaffI = " in text
    assert 'piece = "Guitar"' in text and 'piece = "Bass"' in text
    assert 'opus = "Transcribed by Bob"' in text
    assert '"Performance notes"' in text and '"Use a pick"' in text


def test_bass_score_only():
    bass = score([system([staff([pos(0, 1, notes=[note(3, 0)])], strings=4, clef=1)])],
                 guitars=[guitar(notes=BASS)])
    text = ly(song(None, bass))
    assert "bassStaffI" in text and "piece" not in text


def test_tuning_change_with_clef_change():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])]),
                      system([staff([pos(0, 1, notes=[note(3, 0)])], strings=4, clef=1)])],
                     guitars=[guitar(0), guitar(1, notes=BASS)],
                     guitar_ins=[guitar_in(0, 0, 0, [0]), guitar_in(1, 0, 0, [1])]))
    text = ly(doc)
    body = block(text, "guitarStaffI")
    # The clef change is for the notation staff only; the tab staff gets the
    # new tuning and is redrawn with four lines.
    assert "\\tag #'notation { \\clef \"bass_8\" }" in body
    assert "\\tag #'tab { \\set TabStaff.stringTunings = \\stringTuning <e,, a,, d, g,> \\stopStaff \\startStaff }" in body
    assert "\\removeWithTag #'tab \\guitarStaffI" in text
    assert "\\removeWithTag #'notation \\guitarStaffI" in text
    assert "#(set-global-staff-size 18)" in text
    assert "page-breaking-system-system-spacing" in text and "(padding . 6)" in text


# ---------------------------------------------------------------------------
# Bars, signatures, repeats
# ---------------------------------------------------------------------------

def test_time_and_key_changes():
    doc = one_bar(pos(0, 1, notes=[E6]), pos(2, 2, P.DOTTED, notes=[E6]),
                  pos(4, 1, notes=[E6]), pos(6, 1, notes=[E6]), pos(8, 2, notes=[E6]),
                  barlines=[barline(1, beats=3, value=4, fifths=3, minor=True),
                            barline(3, beats=4, time_flags=0x400000, fifths=-1, cancellation=True),
                            barline(5, time_shown=False, beats=4, time_flags=0x800000, fifths=-1,
                                    key_shown=False, minor=True),
                            barline(7, beats=2, value=4, fifths=0)])
    g = global_(doc)
    assert "\\numericTimeSignature \\time 3/4 \\once \\omit Staff.KeyCancellation \\key fis \\minor" in g
    assert "\\defaultTimeSignature \\time 4/4 \\key f \\major" in g
    assert "\\once \\omit Staff.TimeSignature \\defaultTimeSignature \\time 2/2" in g
    assert "\\once \\omit Staff.KeySignature \\key d \\minor" in g
    assert "(hidden time signature; hidden key change)" in g


def test_bar_lines():
    doc = one_bar(*[pos(i * 2, 1, notes=[E6]) for i in range(6)],
                  start=barline(type=P.Barline.REPEAT_START),
                  barlines=[barline(1, type=P.Barline.REPEAT_END, repeat=3),
                            barline(3, type=P.Barline.REPEAT_START),
                            barline(5, type=P.Barline.DOUBLE),
                            barline(7, type=P.Barline.FREETIME),
                            barline(9, type=P.Barline.FINE)],
                  end_type=P.Barline.REPEAT_END, end_repeat=4)
    g = global_(doc)
    m = marks(doc)
    assert g.startswith("{\n  % Power Tab line 1\n  \\bar \".|:\"")
    assert '\\bar ":|." s4*4 | % bar 2' in g
    assert '\\bar ".|:" s4*4 | % bar 3' in g
    assert '\\bar "||"' in g and '\\bar "!"' in g and '\\bar "|."' in g
    assert g.rstrip().endswith('\\bar ":|."')
    assert '"x3"' in m and '"x4"' in m


def test_back_to_back_repeat_bars_merge():
    doc = one_bar(pos(0, 1, notes=[E6]), pos(3, 1, notes=[E6]),
                  barlines=[barline(1, type=P.Barline.REPEAT_END), barline(2, type=P.Barline.REPEAT_START,
                                                                           letter="B")])
    g = global_(doc)
    assert '\\bar ":|.|:"' in g and g.count("% bar") == 2
    assert "Section B" in staff1(doc)


def test_trailing_empty_bar_is_dropped():
    doc = one_bar(pos(0, 1, notes=[E6]), barlines=[barline(1, type=P.Barline.REPEAT_END, letter="C")])
    g = global_(doc)
    assert g.count("% bar") == 1 and g.rstrip().endswith('\\bar ":|."')
    # A non-plain end bar after the empty bar wins.
    doc = one_bar(pos(0, 1, notes=[E6]), barlines=[barline(1)], end_type=P.Barline.DOUBLE)
    assert global_(doc).rstrip().endswith('\\bar "||"')


def test_final_bar_lines():
    for end_type, glyph in ((P.Barline.DOUBLE, "||"), (P.Barline.BAR, "|.")):
        g = global_(one_bar(pos(0, 1, notes=[E6]), end_type=end_type))
        assert g.rstrip().endswith(f'\\bar "{glyph}"')


def test_power_tab_lines_and_keep_systems():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])]),
                      system([staff([pos(0, 1, notes=[E6])])])]))
    text = ly(doc, keep_systems=True)
    g = block(text, "guitarGlobal")
    assert "% Power Tab line 2" in g and "\\break" in g
    assert "\\autoLineBreaksOff" in text
    assert "\\break" not in block(ly(doc), "guitarGlobal")


def test_alternate_endings():
    doc = song(score([system([staff([pos(i * 2, 1, notes=[E6]) for i in range(4)])],
                             barlines=[barline(1), barline(3, type=P.Barline.REPEAT_END),
                                       barline(5)]),
                      system([staff([pos(0, 1, notes=[E6])])])],
                     endings=[ending(0, 2, numbers=(1,)), ending(0, 4, numbers=(2,), dal_segno=True),
                              ending(1, 0, numbers=(), da_capo=True, dal_segno_segno=True),
                              ending(5, 0)]))
    m = marks(doc)
    assert "#'((volta \"1.\"))" in m
    assert "#'((volta #f) (volta \"2. D.S.\"))" in m
    assert "(volta \"D.C. D.S.S.\")" in m
    assert m.rstrip().endswith("#'((volta #f))")


def test_ending_with_no_numbers():
    m = marks(song(score([system([staff([pos(0, 1, notes=[E6])])])], endings=[ending(0, 0, numbers=())])))
    assert '(volta "1.")' in m


def test_rehearsal_signs():
    doc = one_bar(pos(0, 1, notes=[E6]), start=barline(letter="A", text="Intro"))
    assert '\\mark \\markup { \\box \\bold "A" "Intro" }' in marks(doc)
    assert "% --- Section A: Intro ---" in staff1(doc)
    doc = one_bar(pos(0, 1, notes=[E6]), start=barline(letter="\x01"))
    assert '\\box \\bold "?"' in marks(doc) and "Section ?" in staff1(doc)


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

def test_tempo_markers():
    # Each marker at its own position: LilyPond takes one tempo per moment.
    doc = song(score([system([staff([pos(i, 16, notes=[E6]) for i in range(16)])])],
                     tempos=[tempo(0, 0, 120, description="Rock"), tempo(0, 1, 0, type=2, beat=2, listesso=3),
                             tempo(0, 2, 0, type=3, beat=0), tempo(0, 3, 0, type=3, beat=1),
                             tempo(0, 4, 90, type=0), tempo(0, 5, 0, type=0, description="Freely"),
                             tempo(0, 6, 100, type=1, beat=12), tempo(0, 7, 80, triplet_feel=1),
                             tempo(0, 8, 80, triplet_feel=4), tempo(0, 9, 0, type=0)]))
    m = marks(doc)
    assert '\\tempo "Rock" 4 = 120' in m
    assert "\\tempo \\markup { \\rhythm { 4 } = \\rhythm { 4. } }" in m
    assert '"accel."' in m and '"rit."' in m
    assert "\\set Score.tempoHideNote = ##t \\tempo 4 = 90" in m
    assert '\\tempo "Freely"' in m
    assert "\\tempo 4 = 100" in m                   # unknown beat type -> quarter
    assert '"Triplet feel" \\rhythm { 8[ 8] } = \\rhythm { \\tuplet 3/2 { 4 8 } }' in m
    assert '"Triplet feel (off-beat)" \\rhythm { 16[ 16] }' in m


def test_one_tempo_per_moment():
    # Two at the same position, and one past the last note that lands with them.
    doc = song(score([system([staff([pos(0, 2, notes=[E6]), pos(2, 2, notes=[E6])])])],
                     tempos=[tempo(0, 2, 50, type=3), tempo(0, 2, 60), tempo(0, 2, 70),
                             tempo(0, 9, 80)]))
    m = marks(doc)
    assert "\\tempo 4 = 60" in m
    assert "= 70" not in m and "= 80" not in m
    assert '"rit."' in m                            # other marks stay


def test_listesso_with_unknown_beat():
    m = marks(song(score([system([staff([pos(0, 1, notes=[E6])])])],
                         tempos=[tempo(0, 0, 0, type=2, beat=2, listesso=12)])))
    assert "\\rhythm { 4 } = \\rhythm { 4 }" in m


def test_marks_are_placed_at_their_time():
    doc = song(score([system([staff([pos(0, 2, notes=[E6]), pos(2, 2, notes=[E6])])],
                             chords=[chord_text(0, chord_name(4, 1)), chord_text(1, chord_name(9, 0)),
                                     chord_text(2, chord_name(7, 0)), chord_text(5, chord_name(2, 0))])]))
    m = marks(doc)
    # Position 1 has no note: it takes the time of the next position.
    # Position 5 is after the last note: it goes at the end of the bar.
    assert 's4*2 \\chord "Em" s4*2 \\chord "A" \\chord "G" \\chord "D"' in m


def test_directions():
    doc = one_bar(pos(0, 1, notes=[E6]),
                  directions=[direction(0, (0, 0, 0), (1, 0, 0), (2, 2, 0), (3, 0, 2),
                                        (12, 1, 0), (8, 0, 3), (30, 0, 0))])
    m = marks(doc)
    assert '\\textMark \\markup \\musicglyph "scripts.coda"' in m
    assert '\\concat { \\musicglyph "scripts.varcoda" \\musicglyph "scripts.varcoda" }' in m
    assert '\\line { \\musicglyph "scripts.segno" "(on D.S.)" }' in m
    assert '"(2nd time)"' in m
    assert '"D.S. al Coda (on D.C.)"' in m
    assert '"To Coda (3rd time)"' in m


def test_floating_text():
    doc = song(score([system([staff([pos(i, 4, notes=[E6]) for i in range(4)])], rect=(0, 0, 800, 100)),
                      system([staff([pos(0, 1, notes=[E6])])], rect=(0, 100, 800, 200))],
                     floating_texts=[floating("fade in\r\n* note", rect=(0, 10, 50, 20)),
                                     floating("later", rect=(0, 150, 50, 160)),
                                     floating("lost", rect=(0, 900, 50, 910)),
                                     floating("   ")]))
    m = marks(doc)
    assert '\\fx \\markup \\italic \\column { "fade in" "* note" }' in m
    assert '"later"' in m and '"lost"' in m


def test_floating_text_without_systems():
    conv = L.ScoreConverter(score(floating_texts=[floating("x")]), "g", L.Options())
    assert conv.floating_texts() == {}


def test_offsets_for_marks_in_empty_bars():
    doc = one_bar(pos(0, 1, notes=[E6]), barlines=[barline(2)],
                  chords=[chord_text(3, chord_name(0, 0))])
    doc.guitar_score.systems[0].staves[0].voices[0].append(rest(4, 1))
    assert '\\chord "C" | % bar 2' in marks(doc)


def test_mark_at_end_of_bar():
    conv = L.ScoreConverter(score(), "g", L.Options())
    bar = L.Bar(0, 0, 4, barline(), 0, 0, L.Fraction(1), length=L.Fraction(1))
    line = conv.spacer_line(bar, [(L.Fraction(2), "\\x", False), (L.Fraction(0), "\\y", True)])
    assert line == "\\x s4*4 \\y"


# ---------------------------------------------------------------------------
# Rhythm slashes, chord diagrams, MIDI
# ---------------------------------------------------------------------------

def test_rhythm_slashes():
    slashes = [slash(0, 4, P.SLASH_STACCATO | P.SLASH_PICK_DOWN, beaming=0x04),
               slash(1, 4, P.SLASH_TIED | P.SLASH_MARCATO | P.SLASH_PICK_UP | P.SLASH_ARPEGGIO_UP,
                     beaming=0x10),
               slash(2, 8, P.SLASH_MUTED | P.SLASH_SFORZANDO | P.SLASH_SLIDE_IN_BELOW, single=(5, 3)),
               slash(3, 8, P.SLASH_SLIDE_OUT_DOWN | P.SLASH_REST),
               slash(4, 4, P.SLASH_SLIDE_OUT_DOWN | P.SLASH_TRIPLET_FEEL_1, beaming=0x20),
               slash(5, 4, P.SLASH_SLIDE_OUT_UP | P.SLASH_ARPEGGIO_DOWN, beaming=0x80),
               slash(6, 4, P.SLASH_TIED)]
    doc = song(score([system([staff([rest(0, 1)])], slashes=slashes),
                      system([staff([rest(0, 1)])])],
                     dynamics=[dynamic(0, 0, 0, slash_volume=91), dynamic(0, 0, 9, slash_volume=0xFF)]))
    text = ly(doc)
    s = block(text, "guitarSlashes")
    assert "\\improvisationOn" in s and "\\autoBeamOff" in s
    assert "b'4~ -. \\downbow \\ff" in s
    assert "\\once \\override Arpeggio.arpeggio-direction = #UP b'4 -> \\upbow \\arpeggio" in s
    assert '\\deadNote b\'8 \\fx "3 (string 6)" \\fx "sl." -^ r8' in s
    assert "\\tuplet 3/2 {" in s and "\\bendAfter #+4" in s
    assert "s4*4 | % bar 2" in s
    assert '\\new RhythmicStaff \\with { instrumentName = "Rhythm" }' in text


def test_slash_tie_after_rest_is_ignored():
    doc = song(score([system([staff([rest(0, 1)])],
                             slashes=[slash(0, 2, P.SLASH_REST), slash(1, 2, P.SLASH_TIED)])]))
    assert "~" not in block(ly(doc), "guitarSlashes")


def test_full_bar_slash_rest():
    doc = song(score([system([staff([])], slashes=[slash(0, 1, P.SLASH_REST)])]))
    assert "R4*4" in block(ly(doc), "guitarSlashes")


def test_chord_diagrams():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])])],
                     diagrams=[diagram(chord_name(9, 0), [0, 2, 2, 2, 0, 0xFE]),
                               diagram(chord_name(4, 1), [0, 0, 0, 2, 2, 0, 0xFF]),
                               diagram(chord_name(0, 0), [])]))
    text = ly(doc)
    assert '\\center-column { "A" \\fret-diagram-terse "x;o;2;2;2;o;" }' in text
    assert "(string-count . 7)" in text
    diagrams = text.split("% Chord diagrams.")[1].split("\n}\n")[0]
    assert diagrams.count("center-column") == 2        # the empty diagram is skipped


def test_no_chord_diagrams():
    assert L.chord_diagrams_markup(score()) == ""
    assert L.guitars_markup(score()) == ""


def test_midi_output():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])]), staff([pos(0, 1, notes=[E6])])])],
                     guitars=[guitar(0, preset=29, pan=127, reverb=64, chorus=127, volume=200),
                              guitar(1, preset=200)],
                     guitar_ins=[guitar_in(0, 0, 0, [0]), guitar_in(0, 1, 0, [1])]))
    text = ly(doc, midi=True)
    assert "\\midi { }" in text
    assert 'midiInstrument = "overdriven guitar"' in text
    assert "midiPanPosition = #0.98" in text and "midiReverbLevel = #0.50" in text
    assert "midiChorusLevel = #1.00" in text and "midiMaximumVolume = #1.00" in text
    assert 'midiInstrument = "acoustic grand"' in text
    assert "\\midi" not in ly(doc)


def test_midi_without_guitars():
    conv = L.ScoreConverter(score(), "g", L.Options())
    assert conv.midi_staff("v", [], False) == "    \\new Staff \\with {  }\n      << \\gGlobal \\v >>\n"


def test_many_staves_use_numbers_after_roman_numerals():
    staves = [staff([pos(0, 1, notes=[E6])]) for _ in range(32)]
    text = ly(song(score([system(staves)], guitar_ins=[])))
    assert "guitarStaffIX = " in text and "guitarStaffXXXI = " in text
    assert "guitarStaff32 = " in text


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_dynamic_after_the_last_note_goes_on_the_last_note():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])], barlines=[barline(5)])],
                     dynamics=[dynamic(0, 0, 3, staff_volume=52)]))
    assert "<e,\\6>1 \\mp" in staff1(doc)


def test_guitar_change_with_no_note_after_it_is_not_labelled():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])], barlines=[barline(5)])],
                     guitars=[guitar(0), guitar(1)],
                     guitar_ins=[guitar_in(0, 0, 0, [0]), guitar_in(0, 0, 3, [1])]))
    assert "Gtr. 2" not in staff1(doc)


def test_marks_in_later_systems_and_bars():
    doc = song(score([system([staff([pos(0, 1, notes=[E6]), pos(2, 1, notes=[E6])])],
                             barlines=[barline(1)], directions=[direction(2, (4, 0, 0))]),
                      system([staff([pos(0, 1, notes=[E6])])])],
                     tempos=[tempo(1, 0, 70)]))
    m = marks(doc)
    lines = m.splitlines()
    assert '"Fine"' in [l for l in lines if "bar 2" in l][0]
    assert "\\tempo 4 = 70" in [l for l in lines if "bar 3" in l][0]


def test_staff_that_starts_in_a_later_system():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])]),
                      system([staff([pos(0, 1, notes=[E6])]), staff([pos(0, 1, notes=[note(3, 0)])], strings=4)])],
                     guitars=[guitar(0), guitar(1, notes=BASS)],
                     guitar_ins=[guitar_in(0, 0, 0, [0]), guitar_in(1, 1, 0, [1])]))
    text = ly(doc)
    assert 'instrumentName = "Gtr. 2"' in text and "\\stringTuning <e,, a,, d, g,>" in text


def test_major_chord_with_extension_only():
    assert chord_name(0, 0, modifications=0x01).text() == "C"


def test_clef_change_without_tuning_change():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])]),
                      system([staff([pos(0, 1, notes=[E6])], clef=1)])]))
    body = staff1(doc)
    assert "\\tag #'notation { \\clef \"bass_8\" }" in body
    assert "stringTunings" not in body


# ---------------------------------------------------------------------------
# Ties that can't connect normally, endings, respelling
# ---------------------------------------------------------------------------

def test_tie_into_a_harmonic_chord_becomes_a_repeat_tie():
    body = staff1(one_bar(pos(0, 2, notes=[note(5, 12)]),
                          pos(1, 2, notes=[note(5, 12, P.TIED | P.NATURAL_HARMONIC)])))
    assert "~" not in body and "\\harmonicByFret #12 <e,\\repeatTie\\6>2" in body


def test_tie_out_of_a_harmonic_chord_becomes_a_repeat_tie():
    body = staff1(one_bar(pos(0, 2, notes=[note(5, 12, P.NATURAL_HARMONIC)]),
                          pos(1, 2, notes=[note(5, 0, P.TIED)])))
    assert "~" not in body and "<e,\\repeatTie\\6>2" in body


def test_tie_into_a_slide_in_becomes_a_repeat_tie():
    body = staff1(one_bar(pos(0, 2, notes=[note(2, 5)]),
                          pos(1, 2, notes=[note(2, 5, P.TIED, complex=[slide(into=1)])])))
    assert "~" not in body and "<c'\\repeatTie\\3>2" in body


def test_tie_after_a_grace_note_becomes_a_repeat_tie():
    body = staff1(one_bar(pos(0, 2, notes=[note(0, 0)]),
                          pos(1, 8, P.ACCIACCATURA, notes=[note(0, 2)]),
                          pos(2, 2, notes=[note(0, 0, P.TIED)])))
    assert "~" not in body and "<e'\\repeatTie\\1>2" in body


def test_tie_after_a_missing_staff_becomes_a_repeat_tie():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])]), staff([pos(0, 1, notes=[E6])])]),
                      system([staff([pos(0, 1, notes=[E6])])]),
                      system([staff([pos(0, 1, notes=[E6])]), staff([pos(0, 1, notes=[note(5, 0, P.TIED)])])])],
                     guitar_ins=[guitar_in(0, 0, 0), guitar_in(0, 1, 0)]))
    body = block(ly(doc), "guitarStaffII")
    assert "~" not in body and "\\repeatTie" in body


def test_slash_ties_stop_at_empty_bars():
    doc = song(score([system([staff([rest(0, 1)])], slashes=[slash(0, 1)]),
                      system([staff([rest(0, 1)])]),
                      system([staff([rest(0, 1)])], slashes=[slash(0, 1, P.SLASH_TIED)])]))
    assert "~" not in block(ly(doc), "guitarSlashes")


def test_endings_in_one_bar_share_a_bracket():
    doc = song(score([system([staff([pos(0, 2, notes=[E6]), pos(1, 2, notes=[E6])])])],
                     endings=[ending(0, 0, numbers=(1,)), ending(0, 1, numbers=(2,))]))
    assert "(volta \"1. 2.\")" in marks(doc)


def test_an_ending_stops_where_the_next_one_starts():
    doc = song(score([system([staff([pos(i * 2, 1, notes=[E6]) for i in range(3)])],
                             barlines=[barline(1), barline(3, type=P.Barline.REPEAT_END)])],
                     endings=[ending(0, 0, numbers=(1,)), ending(0, 2, numbers=(2,))]))
    m = marks(doc)
    assert "#'((volta #f) (volta \"2.\"))" in m
    assert m.count("(volta #f)") == 2


def test_transposed_notation_is_respelled_once():
    shifted = score([system([staff([pos(0, 1, notes=[E6])])])], guitars=[guitar(offset=1)])
    text = ly(song(shifted, score([system([staff([pos(0, 1, notes=[note(3, 0)])], strings=4)])],
                                  guitars=[guitar(notes=BASS, offset=1)])))
    assert text.count("naturalizeMusic = ") == 1
    assert "\\naturalizeMusic \\transpose c cis \\guitarStaffI" in text
    assert "\\naturalizeMusic \\transpose c cis \\bassStaffI" in text
    assert "naturalizeMusic" not in ly(one_bar(pos(0, 1, notes=[E6])))


def test_an_ending_stops_at_the_end_of_its_power_tab_line():
    doc = song(score([system([staff([pos(0, 1, notes=[E6])])]),
                      system([staff([pos(0, 1, notes=[E6])])], end_type=P.Barline.REPEAT_END)],
                     endings=[ending(0, 0, numbers=(1,))]))
    lines = marks(doc).splitlines()
    assert "(volta \"1.\")" in [l for l in lines if "bar 1" in l][0]
    assert "(volta #f)" in [l for l in lines if "bar 2" in l][0]
