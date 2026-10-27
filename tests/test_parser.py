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

"""Tests for ptbparser: reading .ptb files into Python objects."""

import struct

import pytest

from ptb2ly import ptbparser as P
from ptbbuilder import (BASS, Writer, barline, chord_name, direction, ending, guitar, note,
                        one_bar, pos, rest, score, slash, song, staff, system, tempo,
                        to_bytes, tuning)


def roundtrip(doc: P.Document) -> P.Document:
    return P.parse_bytes(to_bytes(doc))


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def test_song_header_fields():
    doc = roundtrip(song(title="Hello", artist="Band", composer="C", lyricist="L",
                         arranger="A", guitar_transcriber="G", bass_transcriber="B",
                         copyright="(c)", lyrics="la la", guitar_notes="gn",
                         bass_notes="bn", author_type=0))
    h = doc.header
    assert (h.title, h.artist, h.composer, h.lyricist) == ("Hello", "Band", "C", "L")
    assert (h.arranger, h.guitar_transcriber, h.bass_transcriber) == ("A", "G", "B")
    assert (h.copyright, h.lyrics, h.guitar_notes, h.bass_notes) == ("(c)", "la la", "gn", "bn")


@pytest.mark.parametrize("release_type, expected", [
    (0, ("Album", 1999, True, 2)),
    (1, ("Video", 0, True, 0)),
    (2, ("Boot", 1975, False, 0)),
    (3, ("", 0, False, 0)),
])
def test_release_types(release_type, expected):
    title, year, live, audio = expected
    h = roundtrip(song(release_type=release_type, release_title=title, year=year,
                       live=live, audio_type=audio)).header
    assert (h.release_title, h.year, h.live, h.audio_type) == expected


def test_traditional_author_has_no_composer():
    h = roundtrip(song(author_type=1, composer="ignored")).header
    assert h.author_type == 1 and h.composer == ""


def test_lesson_header():
    doc = song(file_type=P.FILETYPE_LESSON, title="Lesson", subtitle="Sub",
               music_style=17, level=2, author="Teacher", notes="Practice", copyright="c")
    h = roundtrip(doc).header
    assert (h.file_type, h.title, h.subtitle, h.music_style, h.level) == (1, "Lesson", "Sub", 17, 2)
    assert (h.author, h.notes, h.copyright) == ("Teacher", "Practice", "c")


def test_long_strings_use_wider_lengths():
    long_text = "x" * 300            # 0xFF + u16 length
    huge_text = "y" * 70000          # 0xFF + 0xFFFF + u32 length
    h = roundtrip(song(lyrics=long_text, guitar_notes=huge_text)).header
    assert h.lyrics == long_text and h.guitar_notes == huge_text


def test_windows_1252_text():
    assert roundtrip(song(title="It’s")).header.title == "It’s"


def test_undefined_windows_1252_bytes_fall_back_to_latin_1():
    s = P.Stream(b"\x02\x81\x8d")
    assert s.string() == "\x81\x8d"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_not_a_power_tab_file():
    with pytest.raises(P.PtbError, match="not a Power Tab file"):
        P.parse_bytes(b"\0" * 64)


def test_unsupported_version():
    data = bytearray(to_bytes(song()))
    data[4:6] = struct.pack("<H", 3)
    with pytest.raises(P.PtbError, match="unsupported file version 3"):
        P.parse_bytes(bytes(data))


def test_invalid_file_type():
    data = bytearray(to_bytes(song()))
    data[6] = 7
    with pytest.raises(P.PtbError, match="invalid file type"):
        P.parse_bytes(bytes(data))


def test_truncated_file():
    data = to_bytes(one_bar(pos(0, 4, notes=[note(0, 0)])))
    with pytest.raises(P.PtbError, match="unexpected end of file"):
        P.parse_bytes(data[:len(data) - 20])


def test_string_past_end_of_file():
    with pytest.raises(P.PtbError, match="string runs past end"):
        P.Stream(b"\x05ab").string()


def test_trailing_garbage():
    with pytest.raises(P.PtbError, match="unexpected data after the end"):
        P.parse_bytes(to_bytes(song()) + b"junk")


def test_trailing_zeros_are_fine():
    assert P.parse_bytes(to_bytes(song()) + b"\0" * 100).header.title == "Test Song"


def test_counts():
    assert P.Stream(b"\x05\x00").count() == 5
    assert P.Stream(b"\xff\xff\x10\x00\x00\x00").count() == 16
    with pytest.raises(P.PtbError, match="implausible item count"):
        P.Stream(b"\xff\xff\xff\xff\xff\x00").count()


def test_class_tags():
    w = Writer()
    w.class_tag("CThing")
    w.class_tag("CThing")
    s = P.Stream(bytes(w.out))
    s.class_info()
    s.class_info()
    assert s.pos == len(w.out)


def test_big_object_tag():
    # 0x7FFF followed by a 32-bit tag that refers to class 1.
    s = P.Stream(b"\xff\xff\x01\x00\x02\x00CA" + b"\xff\x7f" + struct.pack("<I", 0x80000001))
    s.class_info()
    s.class_info()
    assert s.map_count == 4


@pytest.mark.parametrize("data, message", [
    (b"\x01\x00", "unexpected object tag"),
    (b"\xff\xff\x01\x00\x03\x00x!y", "bad class name"),
    (b"\x05\x80", "unknown class number"),
])
def test_bad_class_tags(data, message):
    with pytest.raises(P.PtbError, match=message):
        P.Stream(data).class_info()


def test_bad_duration():
    bad = pos(0, 4, notes=[note(0, 0)])
    bad.data = (3 << 24)
    with pytest.raises(P.PtbError, match="bad duration 3"):
        roundtrip(one_bar(bad))


def test_too_many_position_symbols():
    with pytest.raises(P.PtbError, match="too many position symbols"):
        roundtrip(one_bar(pos(0, 4, notes=[note(0, 0)], complex=[0, 0, 0])))


def test_too_many_note_symbols():
    with pytest.raises(P.PtbError, match="too many note symbols"):
        roundtrip(one_bar(pos(0, 4, notes=[note(0, 0, complex=[0, 0, 0, 0])])))


def test_bad_string_count():
    with pytest.raises(P.PtbError, match="bad string count 2"):
        roundtrip(song(score([system([staff([rest(0)], strings=2)])])))


def test_parse_file(tmp_path):
    path = tmp_path / "song.ptb"
    path.write_bytes(to_bytes(song(title="From disk")))
    assert P.parse_file(path).header.title == "From disk"


# ---------------------------------------------------------------------------
# Score objects
# ---------------------------------------------------------------------------

def test_structure_roundtrip():
    doc = roundtrip(song(score(
        [system([staff([pos(0, 8, notes=[note(5, 3)])], [rest(0, 1)], strings=6, clef=0),
                 staff([rest(0, 1)], strings=4, clef=1)],
                barlines=[barline(4, type=P.Barline.REPEAT_END, repeat=3)],
                end_type=P.Barline.DOUBLE, end_repeat=2, spacing=25)],
        guitars=[guitar(0), guitar(1, notes=BASS, capo=2, description="Bass")])))
    sc = doc.guitar_score
    sys0 = sc.systems[0]
    assert len(sc.guitars) == 2 and sc.guitars[1].capo == 2
    assert sc.guitars[1].tuning.notes == BASS
    assert (sys0.end_bar_type, sys0.end_bar_repeat_count, sys0.position_spacing) == (1, 2, 25)
    assert (sys0.barlines[0].type, sys0.barlines[0].repeat_count) == (P.Barline.REPEAT_END, 3)
    assert (sys0.staves[0].string_count, sys0.staves[0].clef) == (6, 0)
    assert (sys0.staves[1].string_count, sys0.staves[1].clef) == (4, 1)
    p = sys0.staves[0].voices[0][0]
    assert p.duration == 8 and (p.notes[0].string, p.notes[0].fret) == (5, 3)
    assert sys0.staves[0].voices[1][0].is_rest
    assert not sc.is_empty and doc.bass_score.is_empty


def test_tuning_properties():
    t = tuning(offset=-3, sharps=False)
    assert t.notation_offset == -3 and not t.sharps
    t = tuning(offset=5)
    assert t.notation_offset == 5 and t.sharps


def test_time_signatures():
    assert (barline(beats=6, value=8).time.beats, barline(beats=6, value=8).time.beat_value) == (6, 8)
    common = barline(time_flags=0x400000).time
    cut = barline(time_flags=0x800000).time
    assert (common.beats, common.beat_value, common.common_time) == (4, 4, True)
    assert (cut.beats, cut.beat_value, cut.cut_time) == (2, 2, True)
    assert not barline(time_shown=False).time.shown


def test_key_signatures():
    k = barline(fifths=-3, minor=True, cancellation=True).key
    assert (k.fifths, k.minor, k.cancellation, k.shown) == (-3, True, True, True)
    assert barline(fifths=2).key.fifths == 2
    assert not barline(key_shown=False).key.shown


def test_rehearsal_sign():
    assert barline(letter="B", text="Verse").rehearsal.is_set
    assert not barline().rehearsal.is_set


def test_chord_names():
    assert chord_name(4, 1).text() == "Em"
    assert chord_name(7, 7, bass=11).text() == "G7/B"
    assert chord_name(0, 0, flags=0x10).text() == "N.C."
    assert chord_name(9, 9, flags=0x30).text() == "N.C.(Am7)"
    assert chord_name(9, 0, flags=0x20).text() == "(A)"
    assert chord_name(0, 7, modifications=0x01).text() == "C9"
    assert chord_name(0, 8, modifications=0x02).text() == "Cmaj11"
    assert chord_name(0, 12, modifications=0x04).text() == "Cm/maj13"
    assert chord_name(0, 13, modifications=0x01).text() == "Cm9b5"
    assert chord_name(0, 0, modifications=0x8000 | 0x40).text() == "Csus4add9"
    assert chord_name(1, 0, tonic_variation=0, bass_variation=0).text() == "Bx"
    assert chord_name(1, 0, tonic_variation=0).text() == "Bx/C#"
    assert chord_name(1, 0, tonic_variation=2, bass_variation=2).text() == "Db"


@pytest.mark.parametrize("formula, text", [
    (0, "C"), (1, "Cm"), (2, "C+"), (3, "C°"), (4, "C5"), (5, "C6"), (6, "Cm6"),
    (7, "C7"), (8, "Cmaj7"), (9, "Cm7"), (10, "C+7"), (11, "C°7"), (12, "Cm/maj7"),
    (13, "Cm7b5"),
])
def test_chord_formulas(formula, text):
    assert chord_name(0, formula).text() == text


@pytest.mark.parametrize("bit, text", [
    (0x08, "add2"), (0x10, "add4"), (0x20, "add6"), (0x80, "add11"), (0x100, "b5"),
    (0x200, "+5"), (0x400, "b9"), (0x800, "+9"), (0x1000, "+11"), (0x2000, "b13"),
    (0x4000, "sus2"),
])
def test_chord_modifications(bit, text):
    assert chord_name(0, 0, modifications=bit).text() == "C" + text


def test_chord_extras():
    name = chord_name(0, 0, extra=(2 << 5) | 6)
    assert (name.fret_position, name.chord_type) == (5, 3)
    assert chord_name(0, 0).fret_position is None
    assert chord_name(0, 0, extra=0xFF).chord_type is None


def test_tempo_marker_fields():
    t = tempo(bpm=96, type=2, beat=3, listesso=4, triplet_feel=1)
    assert (t.bpm, t.type, t.beat_type, t.listesso_beat_type, t.triplet_feel) == (96, 2, 3, 4, 1)


def test_alternate_ending_fields():
    e = ending(0, 0, numbers=(1, 3), da_capo=True, dal_segno=True, dal_segno_segno=True)
    assert e.numbers == [1, 3] and e.da_capo and e.dal_segno and e.dal_segno_segno


def test_direction_decoding():
    assert direction(0, (12, 2, 3)).decoded() == [(12, 2, 3)]


def test_guitar_in_and_dynamic_bytes():
    doc = roundtrip(song(score([system([staff([rest(0)])])],
                               guitar_ins=[P.GuitarIn(0, 0, 0, 0x0203)],
                               dynamics=[P.Dynamic(0, 0, 0, (78 << 8) | 39)])))
    gi = doc.guitar_score.guitar_ins[0]
    d = doc.guitar_score.dynamics[0]
    assert (gi.staff_guitars, gi.slash_guitars) == (2, 3)
    assert (d.staff_volume, d.slash_volume) == (78, 39)


def test_rhythm_slash_fields():
    s = slash(3, 8, P.SLASH_DOTTED | P.SLASH_TIED, beaming=0x20 | 0x04, single=(2, 7))
    assert (s.duration, s.dots, s.single_note) == (8, 1, (2, 7))
    assert s.triplet_start and s.beam_start and not s.triplet_end and not s.beam_end
    assert slash(0, 4, P.SLASH_DOUBLE_DOTTED).dots == 2
    assert slash(0).single_note is None


def test_position_fields():
    p = pos(0, 8, P.DOUBLE_DOTTED | P.GROUP_START, notes=[note(0, 0)],
            beaming=(4 << 3) | 2 | 0x400 | 0x2000,
            complex=[(ord("j") << 24) | 3, (ord("c") << 24) | (1 << 16) | (2 << 8) | 4])
    assert p.dots == 2 and p.tuplet == (5, 3) and p.beam_start and p.beam_end
    assert p.multibar_rest == 3 and p.tremolo_bar == (1, 2, 4)
    assert p.volume_swell is None
    swell = pos(0, complex=[(ord("a") << 24) | (13 << 16) | (78 << 8) | 2])
    assert swell.volume_swell == (13, 78, 2)
    assert pos(0, 4, P.DOTTED).dots == 1 and pos(0).dots == 0


def test_note_fields():
    n = note(3, 12, P.TIED | P.HAMMER_ON, complex=[
        (ord("d") << 24) | (1 << 16) | (2 << 8) | 0xFE,
        (ord("e") << 24) | (2 << 20) | (3 << 8) | (4 << 4) | 1,
        (ord("g") << 24) | (14 << 16),
    ])
    assert (n.string, n.fret) == (3, 12)
    assert n.hammer_on and not n.pull_off
    assert n.slide == (1, 2, -2)
    assert n.bend == (2, 4, 1, 3)
    assert n.trill == 14
    assert n.tapped_harmonic is None and n.artificial_harmonic is None
    th = note(0, 5, complex=[(ord("f") << 24) | 17, (ord("h") << 24) | (1 << 16) | (1 << 8) | 4])
    assert th.tapped_harmonic == 17 and th.artificial_harmonic == (4, 1, 1)
    assert th.slide is None and th.bend is None and th.trill is None
    assert note(0, 0, P.PULL_OFF).pull_off


def test_position_from_x():
    s = system([staff([rest(0)])], start=barline(fifths=2, beats=4), spacing=20, rect=(10, 0, 800, 100))
    # first position x = 10 + 22 + 12 (key) + 18 (time) + 3 + 1 (bar) = 66
    assert s.position_from_x(66 + 20 * 3) == 2
    assert s.position_from_x(0) == 0
    flat = system([staff([rest(0)])], start=barline(fifths=-2, time_shown=False,
                                                     type=P.Barline.REPEAT_START))
    assert flat.position_from_x(500) > 0


def test_stream_helpers():
    s = P.Stream(struct.pack("<iiii", 1, 2, 3, 4) + b"\x02\x01\x00\x02\x00")
    assert s.rect() == (1, 2, 3, 4)
    assert s.small_vector_u16() == [1, 2]


def test_every_symbol_roundtrips():
    from ptbbuilder import chord_text, diagram, floating
    doc = roundtrip(song(score(
        [system([staff([rest(0)])],
                directions=[direction(0, (2, 0, 0))],
                chords=[chord_text(0, chord_name(9, 1))],
                slashes=[slash(0, 4, single=(1, 3))])],
        tempos=[tempo(bpm=88, description="Slow")],
        endings=[ending(0, 0, numbers=(2,))],
        diagrams=[diagram(chord_name(9, 0), [0, 2, 2, 2, 0, 0xFE], top=1)],
        floating_texts=[floating("fade in", rect=(5, 6, 7, 8))])))
    sc = doc.guitar_score
    s = sc.systems[0]
    assert s.directions[0].decoded() == [(2, 0, 0)]
    assert s.chord_texts[0].name.text() == "Am"
    assert s.rhythm_slashes[0].single_note == (1, 3)
    assert (sc.tempo_markers[0].bpm, sc.tempo_markers[0].description) == (88, "Slow")
    assert sc.alternate_endings[0].numbers == [2]
    assert sc.chord_diagrams[0].frets == [0, 2, 2, 2, 0, 0xFE]
    assert sc.chord_diagrams[0].top_fret == 1
    assert (sc.floating_texts[0].text, sc.floating_texts[0].rect) == ("fade in", (5, 6, 7, 8))
    assert s.staves[0].voices[0][0].tremolo_bar is None


def test_position_from_x_without_key_signature():
    s = system([staff([rest(0)])], start=barline(fifths=3, key_shown=False), spacing=10)
    assert s.position_from_x(22 + 18 + 1 + 10 * 5) == 4
