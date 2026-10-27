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

"""Command line: python -m ptb2ly INPUT [INPUT ...] [-o OUTDIR]"""

import argparse
import sys
from pathlib import Path

from .lilypond import Options, convert_document
from .ptbparser import PtbError, parse_file


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ptb2ly",
                                 description="Convert Power Tab (.ptb) files to LilyPond (.ly).")
    ap.add_argument("inputs", nargs="+", type=Path, help=".ptb files or directories")
    ap.add_argument("-o", "--outdir", type=Path,
                    help="output directory (default: next to each input file)")
    ap.add_argument("--no-lyrics", action="store_true",
                    help="don't print the song's lyrics text after the score")
    ap.add_argument("--midi", action="store_true",
                    help="also write a MIDI file when LilyPond typesets the score")
    ap.add_argument("--keep-systems", action="store_true",
                    help="break lines where Power Tab did, instead of letting LilyPond decide")
    args = ap.parse_args(argv)

    files = []
    for p in args.inputs:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.ptb")))
        else:
            files.append(p)

    failures = 0
    for f in files:
        out_dir = args.outdir or f.parent
        out = out_dir / (f.stem + ".ly")
        try:
            doc = parse_file(f)
            options = Options(lyrics=not args.no_lyrics, midi=args.midi,
                              keep_systems=args.keep_systems, source_name=f.name)
            text = convert_document(doc, options=options)
        except PtbError as e:
            print(f"skipped {f}: {e}", file=sys.stderr)
            failures += 1
            continue
        except Exception as e:  # converter bug: report and keep going
            print(f"failed {f}: {type(e).__name__}: {e}", file=sys.stderr)
            failures += 1
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        if len(files) == 1:
            print(out)
    if len(files) > 1:
        print(f"converted {len(files) - failures} of {len(files)} files", file=sys.stderr)
    return 1 if failures and failures == len(files) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
