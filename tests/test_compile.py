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

"""Typesets converter output with LilyPond and checks for errors and warnings.

Skipped when LilyPond isn't installed.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from ptb2ly import lilypond as L
from ptb2ly import ptbparser as P
from ptbbuilder import (BASS, barline, chord_name, chord_text, diagram, direction, dynamic,
                        ending, floating, guitar, guitar_in, note, pos, rest, score, slash,
                        song, staff, system, tempo, to_bytes)

DATA = Path(__file__).parent / "data"

pytestmark = pytest.mark.skipif(not shutil.which("lilypond"), reason="LilyPond not installed")


def kitchen_sink() -> P.Document:
    """One song that uses every feature the converter supports."""
    slide_out = (ord("d") << 24) | (1 << 8)
    legato = (ord("d") << 24) | (2 << 8)
    slide_in = (ord("d") << 24) | (1 << 16)
    fall = (ord("d") << 24) | (3 << 8)
    bend = (ord("e") << 24) | (4 << 4)
    release = (ord("e") << 24) | (6 << 20) | (4 << 4) | 2
    trill = (ord("g") << 24) | (9 << 16)
    tapped = (ord("f") << 24) | 19
    artificial = (ord("h") << 24) | (1 << 16) | (1 << 8) | 4
    bar_dip = (ord("c") << 24) | 4
    swell = (ord("a") << 24) | (13 << 16) | (91 << 8)
    s, e = 0x400, 0x2000

    bar1 = [  # 4/4 with tuplets, grace notes, slides, beams
        pos(0, 8, P.ACCIACCATURA, notes=[note(2, 2)]),
        pos(1, 8, P.GROUP_START | P.PALM_MUTE, notes=[note(2, 4, P.HAMMER_ON)], beaming=(2 << 3) | 1 | s),
        pos(2, 8, P.GROUP_MIDDLE | P.PALM_MUTE, notes=[note(2, 5, P.PULL_OFF)]),
        pos(3, 8, P.GROUP_END | P.PALM_MUTE, notes=[note(2, 4)], beaming=e),
        pos(4, 4, P.STACCATO | P.PICK_DOWN, notes=[note(3, 2, complex=[slide_out])]),
        pos(5, 4, P.MARCATO | P.PICK_UP, notes=[note(3, 4, complex=[legato])]),
        pos(6, 4, P.SFORZANDO, notes=[note(3, 7)]),
    ]
    bar2 = [  # effects
        pos(8, 4, P.VIBRATO | P.LET_RING, notes=[note(1, 5, complex=[bend])]),
        pos(9, 4, P.LET_RING, notes=[note(1, 5, complex=[release])]),
        pos(10, 4, P.WIDE_VIBRATO, notes=[note(0, 5, complex=[trill])]),
        pos(11, 4, P.TAP, notes=[note(0, 7, complex=[tapped]), note(1, 5, complex=[artificial])]),
    ]
    bar3 = [  # chords, harmonics, dead and ghost notes, ties
        pos(13, 4, P.ARPEGGIO_UP, notes=[note(5, 0), note(4, 2), note(3, 2)]),
        pos(14, 4, P.ARPEGGIO_DOWN, notes=[note(5, 12, P.NATURAL_HARMONIC), note(4, 12, P.NATURAL_HARMONIC)]),
        pos(15, 4, notes=[note(5, 7, P.NATURAL_HARMONIC), note(4, 5)]),
        pos(16, 8, notes=[note(1, 0, P.MUTED), note(0, 0, P.GHOST)]),
        pos(17, 8, notes=[note(1, 1), note(0, 0, P.TIED)]),
    ]
    bar4 = [  # octave signs, tremolo, swells, tremolo bar, slide in and fall
        pos(19, 4, P.TREMOLO_PICKING, notes=[note(0, 12, P.OCTAVE_8VA)], complex=[swell]),
        pos(20, 4, P.FERMATA, notes=[note(0, 12, P.OCTAVE_8VA)], complex=[bar_dip]),
        pos(21, 4, notes=[note(2, 5, complex=[slide_in])]),
        pos(22, 4, notes=[note(2, 5, complex=[fall])]),
    ]
    voice1 = bar1 + bar2 + bar3 + bar4
    voice2 = [pos(13, 2, notes=[note(5, 0)]), pos(15, 2, notes=[note(5, 3)])]
    sys1 = system(
        [staff(voice1, voice2), staff([rest(0, 1), pos(8, 1, notes=[note(5, 0)]), rest(13, 1), rest(19, 1)])],
        start=barline(letter="A", text="Intro", type=P.Barline.REPEAT_START),
        barlines=[barline(7), barline(12, type=P.Barline.REPEAT_END, repeat=3),
                  barline(18, beats=4, fifths=-2)],
        directions=[direction(13, (2, 0, 0)), direction(22, (12, 0, 0))],
        chords=[chord_text(0, chord_name(9, 1)), chord_text(13, chord_name(4, 1, extra=1))],
        slashes=[slash(0, 4, beaming=0x04), slash(1, 4, P.SLASH_TIED, beaming=0x10), slash(2, 2, P.SLASH_MUTED),
                 slash(8, 8, single=(5, 3)), slash(9, 8, P.SLASH_REST), slash(10, 4, beaming=0x20),
                 slash(11, 4), slash(12, 4, beaming=0x80), slash(13, 2)],
    )
    sys2 = system(  # time change, pickup-length bar, repeat endings
        [staff([pos(0, 4, notes=[note(5, 0)]), pos(1, 4, notes=[note(5, 0)]), pos(2, 4, notes=[note(5, 0)]),
                pos(4, 4, notes=[note(4, 0)]), pos(5, 2, P.DOTTED, notes=[note(4, 0)]),
                pos(7, 1, complex=[(ord("j") << 24) | 2])], strings=7)],
        start=barline(beats=3, value=4, letter="B", text="Verse"),
        barlines=[barline(3, beats=4, time_flags=0x400000), barline(6, type=P.Barline.REPEAT_END)],
        end_type=P.Barline.FINE,
    )
    guitars = [guitar(0, preset=27), guitar(1, notes=[62, 59, 55, 50, 45, 38], capo=2, tuning_name="Drop D"),
               guitar(2, notes=[64, 59, 55, 50, 45, 40, 35], tuning_name="7 string", offset=-12)]
    guitar_score = score(
        [sys1, sys2], guitars=guitars,
        guitar_ins=[guitar_in(0, 0, 0, [0]), guitar_in(0, 1, 0, [1]), guitar_in(0, 1, 13, [0, 1]),
                    guitar_in(1, 0, 0, [2])],
        tempos=[tempo(0, 0, 112, description="Moderately", triplet_feel=1), tempo(0, 13, 0, type=3, beat=1),
                tempo(1, 0, 0, type=2, beat=2, listesso=3)],
        dynamics=[dynamic(0, 0, 0, staff_volume=65, slash_volume=78), dynamic(0, 0, 8, staff_volume=104)],
        endings=[ending(0, 8, numbers=(1, 2)), ending(1, 4, numbers=(3,))],
        diagrams=[diagram(chord_name(9, 1), [0, 1, 2, 2, 0, 0xFE]), diagram(chord_name(4, 1), [0, 0, 0, 2, 2, 0])],
        floating_texts=[floating("w/ distortion", rect=(200, 10, 300, 20))],
    )
    bass = score([system([staff([pos(0, 2, notes=[note(3, 0)]), pos(1, 2, notes=[note(3, 3)])],
                                strings=4, clef=1)])],
                 guitars=[guitar(notes=BASS, preset=33)])
    return song(guitar_score, bass, title="Kitchen Sink", release_type=0, release_title="Tests",
                year=2026, lyrics="First line\r\nSecond line", guitar_notes="Play it loud")


def lilypond_problems(text: str, tmp_path: Path):
    ly = tmp_path / "song.ly"
    ly.write_text(text, encoding="utf-8")
    result = subprocess.run(["lilypond", "-l", "WARNING", "-dno-print-pages", "-o", str(tmp_path), str(ly)],
                            capture_output=True, text=True)
    problems = [line for line in result.stderr.splitlines()
                if "warning" in line or "error" in line]
    return result.returncode, problems


def test_kitchen_sink_compiles_cleanly(tmp_path):
    doc = P.parse_bytes(to_bytes(kitchen_sink()))
    text = L.convert_document(doc, options=L.Options(midi=True, keep_systems=True))
    code, problems = lilypond_problems(text, tmp_path)
    assert code == 0 and problems == [], "\n".join(problems)


def test_files_in_test_data_compile(tmp_path):
    files = sorted(DATA.glob("*.ptb"))
    if not files:
        pytest.skip("no .ptb files in tests/data/")
    for f in files:
        text = L.convert_document(P.parse_file(f))
        code, problems = lilypond_problems(text, tmp_path)
        assert code == 0 and problems == [], f"{f.name}:\n" + "\n".join(problems)
