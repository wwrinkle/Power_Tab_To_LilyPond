#!/usr/bin/env bash
# Convert a random sample of Power Tab files to LilyPond and typeset them.
#
# Usage: scripts/sample-build.sh [COUNT] [OUTDIR]
#   COUNT   number of random .ptb files (default 500)
#   OUTDIR  where the .ly and .pdf files go (default out-sample)
set -euo pipefail

count="${1:-500}"
outdir="${2:-out-sample}"
library="instant-song-library/Instant Song Library Piower Tabs"
ptb2ly="${PTB2LY:-.venv/bin/ptb2ly}"

cd "$(dirname "$0")/.."
mkdir -p "$outdir"

# Pick the files and convert them (invalid files are reported and skipped).
find "$library" -name '*.ptb' -print0 | shuf -z -n "$count" | xargs -0 "$ptb2ly" -o "$outdir"

# Typeset every .ly in parallel, one LilyPond job per CPU core.
find "$outdir" -name '*.ly' -print0 | xargs -0 -P "$(nproc)" -n 1 lilypond -s -o "$outdir"

echo "PDFs: $(find "$outdir" -name '*.pdf' | wc -l) of $(find "$outdir" -name '*.ly' | wc -l) in $outdir/"
