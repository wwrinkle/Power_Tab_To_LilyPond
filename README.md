# ptb2ly — Power Tab to LilyPond

Converts Power Tab Editor 1.7 files (`.ptb`) into LilyPond source (`.ly`):
standard notation and tablature for each staff, plus chord names, section
letters, tempo, repeats and endings.

Needs Python 3.8+ (no extra packages) and LilyPond 2.26 to typeset the output.

## Install

```sh
pip install .        # or: pipx install .
```

This adds a `ptb2ly` command. For development, use `pip install -e .` in a
virtual environment.

## Usage

```sh
# one file -> writes song.ly next to it
ptb2ly "path/to/song.ptb"

# a whole folder, output somewhere else
ptb2ly "instant-song-library/Instant Song Library Piower Tabs" -o out/

# then typeset
lilypond out/song.ly
```

Options:

- `-o DIR`: write the `.ly` files to `DIR` instead of next to each input.
- `--midi`: also produce a MIDI file when LilyPond typesets the score
  (instrument, volume, pan, reverb and chorus come from each guitar).
- `--keep-systems`: break lines where Power Tab did, instead of letting
  LilyPond lay out the page.
- `--no-lyrics`: leave out the lyrics text that is otherwise printed after
  the score.

Files that can't be read are reported and skipped, and the batch carries on.

## The output

Each `.ly` file starts with a short guide to reading it, and shorthands for
guitar effects (`\pmOn`, `\bendUp "full"`, `\slideIn`, …) so the music
lines stay readable. The music is written one bar per line, with a
`% bar N` comment matching the printed bar numbers and a comment at each
section letter:

```lilypond
guitarStaffI = {
  \autoBeamOff
  % --- Section A: Intro ---
  <e~\5 e,~\6>1 | % bar 1
  <g\4 e\5>8[ <e,\6>8 \pmOn <e,\6>8 \pmOff <g\4 e\5>8] r2 | % bar 2
}
```

Each chord lists one pitch per string (`\6` = 6th string), lowest string
first. Pitches are the sounding pitches; the tab staff works out the frets.

## What gets converted

| Power Tab | LilyPond output |
|---|---|
| Staves | A notation staff + tab staff per staff, with each guitar's tuning and capo |
| Two voices per staff | `<< {…} \\ {…} >>` |
| Rhythm slashes | A "Rhythm" staff with slash note heads; single-note slashes labelled with fret and string |
| Durations, dots, tuplets | Native rhythms, `\tuplet` |
| Grace notes | `\acciaccatura`, `\appoggiatura` |
| Beams | As drawn in Power Tab |
| Time/key signatures | `\time`, `\key`, including hidden signatures and key cancellations |
| Bars that don't match the time signature | Their real length, so every staff stays aligned |
| Bar lines, repeats, endings | `\bar`, "x3" repeat counts, volta brackets (ending where Power Tab ends them) |
| Multibar rests | Compressed multi-bar rests |
| Tempo markers | `\tempo`, listesso (♩ = ♩.), accel./rit., triplet feel, hidden tempos |
| Rehearsal signs | Boxed section letters |
| Coda, segno, D.C., D.S., Fine… | Symbols and text, with "on D.S." / "2nd time" details |
| Chord names | Text above the score, same spelling as Power Tab, plus fret position and type |
| Chord diagrams | Fret diagrams at the top of the score |
| Floating text | Text above the score at the nearest position |
| Dynamics | `\p`, `\mf`, … (staff and rhythm-slash dynamics) |
| Ties | Ties; a tie with no note right before it gets a short "repeat tie" |
| Hammer-ons, pull-offs | Slurs; "H"/"P" for hammer-on from / pull-off to nowhere |
| Slides | Slide lines between notes, slide in from above/below, slide off up/down |
| Bends | An arrow and the amount ("full", "½", "pre full & rel.") |
| Vibrato, wide vibrato | A wavy line |
| Trills | Trill sign with the fret to trill to |
| Natural harmonics | Diamond notes; sounding pitch in the notation when a chord is all harmonics at one fret |
| Tapped and artificial harmonics | Diamond notes; the tab shows the fret held and the fret touched or tapped, e.g. `7(19)`; one "A.H. 8va" / "T.H." label per run |
| Palm muting, let ring | Dashed "P.M." line, "let ring" label |
| Dead notes, ghost notes | `\deadNote`, parentheses |
| Accents, staccato, fermata, pick strokes, arpeggios, tremolo picking, tapping | Native articulations |
| Tremolo bar (whammy) | A small graph of the pitch (dip, dive, return, …) with the amount in steps, e.g. "w/bar −½" |
| Volume swells | Crescendo/decrescendo hairpins |
| 8va, 15ma, 8vb, 15mb | Octave lines |
| Guitar In | Tuning changes and boxed "Gtr. N" labels where a guitar takes over a staff |
| Tuning notation offset | The notation staff is transposed; the tab is unchanged |
| Guitar and bass scores | Separate scores, labelled "Guitar" and "Bass" |
| Song info | Title, artist, album/video/bootleg and year, composer, lyricist, arranger, transcribers, copyright |
| Performance notes, lesson notes, lyrics | Text blocks after the score |
| Lessons | Title, subtitle, style, level and author |

Staves that only have rests on a line are hidden, as in Power Tab.

### Not converted

These are left out because LilyPond can't express them, or Power Tab keeps
them for its own playback or screen layout:

- **Bend curves.** LilyPond's bend lines need a target note, which Power Tab
  doesn't store, so bends are shown as an arrow and the amount.
- **Triplet feel in playback.** It is shown as a text mark; the notes on
  each position aren't swung in the MIDI file.
- **MIDI tremolo, phaser and fade in/out.** LilyPond's MIDI output has no
  equivalent. Repeats play once.
- **Metronome pulses per bar, fonts and spacing.** These only affect Power
  Tab's own playback and screen layout.

## Library status

All 2,964 files in `instant-song-library/` convert.

43 corrupted files were moved out of the library into `corrupted-ptb/`:

- `corrupted-ptb/blank/` (37 files): every byte is zero. Nothing can be
  recovered from them.
- `corrupted-ptb/cr-stripped/` (6 files): every `0x0D` byte has been
  stripped (damage from an old text-mode file transfer), which shifts all the
  data after the first one. An automatic repair was tried and didn't work:
  bytes lost inside text (lyrics, notes) aren't noticed until well past the
  text, so the right places to re-insert them can't be found reliably.

### Open issues

`scripts/check-library.sh` converts and typesets the whole library and
collects LilyPond's warnings. The last complete run (before the fixes below)
had no conversion errors and no LilyPond failures, only layout warnings.

Fixed since that run; a fresh run will confirm the library-wide numbers:

- Long lyrics and notes ran off the bottom of the page (171 songs). They
  now continue onto the next page.
- Over-full pages (~700 songs, mostly mild). Page breaking now plans for
  extra room between lines of music, and labels above notes take up room on
  the line instead of piling up; on samples, few crowded pages remain.
- Two tempo marks at the same moment (3 songs) and hairpins too short to
  draw (7 songs).
- Harmonics and whammy bar were text labels on every note, stacking into
  tall towers. They are now drawn as in guitar books: diamond notes with
  `7(19)` in the tab, and small pitch graphs for the whammy bar.

Still open:

- **"No solution found for Bezier intersection"** (17 songs). A LilyPond
  internal message, probably from an unusual slur, tie or slide curve. The
  PDF is still written. The construct that triggers it hasn't been found.
- **Remaining crowded pages.** A few songs with very dense effects may
  still get an over-full page; to be measured on the next full run.
- **Artificial harmonics with unusual intervals.** Power Tab stores only the
  harmonic's note name and octave. It is written at or above the fretted
  note; when that isn't a real harmonic interval (an octave, octave + fifth,
  two octaves, ...), the tab shows just the fret held.
- **Whammy bar length.** Graphs are a fixed size; Power Tab's duration (how
  many notes the graph spans) is ignored. Every file in the library uses
  the default, so nothing is lost there.
- **Check script quirks.** A song whose name ends in "." gets a PDF without
  the final dot, and an interrupted check can leave `lilypond-tmp-*.pdf`
  files behind.

## Code layout

- `src/ptb2ly/ptbparser.py` — reads the binary file into Python objects.
- `src/ptb2ly/lilypond.py` — turns those objects into LilyPond text.
- `src/ptb2ly/__main__.py` — command line.
- `tests/` — tests, with 100% line and branch coverage.
  `tests/ptbbuilder.py` writes `.ptb` files from Python, so each test
  describes a small song in code. `tests/test_compile.py` typesets a song
  that uses every feature and fails on any LilyPond warning (skipped if
  LilyPond isn't installed). `tests/data/` is for files you make yourself in
  Power Tab Editor; never copy files from the song library there.

Run the tests:

```sh
pip install -e ".[test]"
coverage run -m pytest
coverage report          # fails below 100%
```

- `reference/powertabeditor/` — a local, untracked clone of the
  [Power Tab Editor 2.0 source](https://github.com/powertab/powertabeditor)
  (GPL; checked against commit `8b23e9d`), kept for reference only. Clone it
  there yourself to follow along. The parser is a port of
  `source/formats/powertab_old/powertabdocument/`, and
  `source/formats/powertab_old/powertaboldimporter.cpp` shows how each field
  is meant to be interpreted.

## The .ptb format in brief

An MFC `CArchive`: little-endian integers, and these building blocks:

- **Count:** `u16`; if `0xFFFF`, a `u32` follows.
- **String:** length as `u8` (if `0xFF` → `u16`, if `0xFFFF` → `u32`), then
  Windows-1252 bytes.
- **Object array:** count, then for each element an MFC class tag (`u16`;
  `0xFFFF` = new class, followed by `u16` schema, `u16` name length and the
  class name, e.g. `CPosition`; `0x8000|n` = a class seen before) and then
  the object's fields. MFC numbers classes and objects in the order they
  appear (starting at 1), and `n` is the number the class got.

Top-level layout (v1.7, version number 4):

```
"ptab"  u16 version  u8 fileType (0 song, 1 lesson)  header strings…
Score (guitar)   Score (bass)   3 × FontSetting   i32 lineSpacing  u32 fadeIn  u32 fadeOut

Score    = [Guitar] [ChordDiagram] [FloatingText] [GuitarIn] [TempoMarker]
           [Dynamic] [AlternateEnding] [System]
System   = rect(4×i32) u8 endBar u8×4 spacing  Barline(startBar)
           [Direction] [ChordText] [RhythmSlash] [Staff] [Barline]
Staff    = u8 (clef<<4 | stringCount) u8×4 spacing  [Position](voice 1) [Position](voice 2)
Position = u8 position  u16 beaming  u32 data  u8 n + n×u32 complexSymbols  [Note]
Note     = u8 (string<<5 | fret)  u16 flags  u8 n + n×u32 complexSymbols
Barline  = u8 position  u8 (type<<5 | repeatCount)  u8 key  u32 time  u8 pulses
           i8 rehearsalLetter  string rehearsalText
Guitar   = u8 number  string name  u8×8 (preset, volume, pan, reverb, chorus,
           tremolo, phaser, capo)  Tuning(string name, u8 flags, u8 n + n×u8 MIDI notes)
```

Things worth knowing:

- **Positions are slots, not times.** A position's index is just where it sits
  on the line; its length comes from the duration in the top byte of `data`
  (1, 2, 4 … 64) plus the dot and tuplet flags. Barlines occupy slots too:
  a note belongs to the bar whose barline slot is at or before it.
- **Strings are numbered from the highest** (0 = high E). Tuning notes are
  stored high to low. Sounding pitch = tuning note + capo + fret.
- **Complex symbols** (bends, slides, harmonics, multibar rests, …) are `u32`s
  whose top byte is an ASCII letter naming the type (`'e'` = bend,
  `'d'` = slide, `'j'` = multibar rest, …).
- **Guitar In** symbols decide which guitar (and so which tuning) is on each
  staff, and the assignment can change from one system to the next.
- **Ties** are flagged on the *second* note; hammer-ons/pull-offs on the *first*.
