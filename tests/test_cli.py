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

"""Tests for the ptb2ly command line."""

import subprocess
import sys

import pytest

from ptb2ly import __main__ as cli
from ptbbuilder import note, one_bar, pos, to_bytes

SONG = to_bytes(one_bar(pos(0, 1, notes=[note(5, 0)])))


def test_single_file_written_next_to_input(tmp_path, capsys):
    src = tmp_path / "song.ptb"
    src.write_bytes(SONG)
    assert cli.main([str(src)]) == 0
    out = tmp_path / "song.ly"
    assert capsys.readouterr().out.strip() == str(out)
    text = out.read_text(encoding="utf-8")
    assert '% Converted from "song.ptb"' in text and "\\midi" not in text


def test_options(tmp_path):
    src = tmp_path / "song.ptb"
    src.write_bytes(SONG)
    outdir = tmp_path / "out" / "nested"
    assert cli.main([str(src), "-o", str(outdir), "--midi", "--keep-systems", "--no-lyrics"]) == 0
    text = (outdir / "song.ly").read_text(encoding="utf-8")
    assert "\\midi { }" in text and "\\autoLineBreaksOff" in text


def test_directory_with_bad_files(tmp_path, capsys):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "good.ptb").write_bytes(SONG)
    (tmp_path / "blank.ptb").write_bytes(b"\0" * 100)
    assert cli.main([str(tmp_path)]) == 0
    err = capsys.readouterr().err
    assert "skipped" in err and "not a Power Tab file" in err
    assert "converted 1 of 2 files" in err
    assert (tmp_path / "sub" / "good.ly").exists()
    assert not (tmp_path / "blank.ly").exists()


def test_all_files_failing_returns_an_error(tmp_path):
    (tmp_path / "blank.ptb").write_bytes(b"\0" * 100)
    assert cli.main([str(tmp_path / "blank.ptb")]) == 1


def test_converter_bug_is_reported_and_batch_continues(tmp_path, capsys, monkeypatch):
    (tmp_path / "a.ptb").write_bytes(SONG)
    (tmp_path / "b.ptb").write_bytes(SONG)
    calls = []

    def flaky(doc, options):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return "% ok\n"

    monkeypatch.setattr(cli, "convert_document", flaky)
    assert cli.main([str(tmp_path)]) == 0
    err = capsys.readouterr().err
    assert "failed" in err and "RuntimeError: boom" in err
    assert (tmp_path / "b.ly").read_text() == "% ok\n"


def test_help_runs_as_a_module():
    result = subprocess.run([sys.executable, "-m", "ptb2ly", "--help"],
                            capture_output=True, text=True)
    assert result.returncode == 0 and "--keep-systems" in result.stdout
