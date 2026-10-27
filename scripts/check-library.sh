#!/usr/bin/env bash
# Convert every song in the library to LilyPond and typeset it to PDF,
# checking for errors and warnings along the way.
#
# Usage: scripts/check-library.sh [OUTDIR]     (default: check-output)
#
# The check can be stopped or interrupted (e.g. by a restart) and run again:
# songs that already have a finished log are skipped.
#
# Results in OUTDIR:
#   ly/          the converted .ly files
#   pdf/         the typeset PDFs
#   logs/        one LilyPond log per song; the last line is "exit N"
#   progress     how far the check has got (updated as it runs)
#   summary.txt  totals and the most common warnings, written at the end
set -uo pipefail

cd "$(dirname "$0")/.."
outdir="${1:-check-output}"
library="instant-song-library/Instant Song Library Piower Tabs"
ptb2ly="${PTB2LY:-.venv/bin/ptb2ly}"
mkdir -p "$outdir/ly" "$outdir/pdf" "$outdir/logs"

total=$(find "$library" -name '*.ptb' | wc -l)

# 1. Convert songs that don't have a .ly yet.
find "$library" -name '*.ptb' -print0 |
    while IFS= read -r -d '' f; do
        name=$(basename "$f" .ptb)
        [ -e "$outdir/ly/$name.ly" ] || printf '%s\0' "$f"
    done |
    xargs -0 -r "$ptb2ly" -o "$outdir/ly" 2> "$outdir/convert-errors.txt"
echo "converted: $(find "$outdir/ly" -name '*.ly' | wc -l) of $total" | tee "$outdir/progress"

# 2. Compile each .ly that has no finished log. Each log is written to a
#    temporary name first, so an interrupted compile never looks finished.
compile_one() {
    ly="$1"; outdir="$2"
    name=$(basename "$ly" .ly)
    log="$outdir/logs/$name.ly.log"
    lilypond -l WARNING -o "$outdir/pdf/$name" "$ly" > "$log.part" 2>&1
    echo "exit $?" >> "$log.part"
    mv "$log.part" "$log"
}
export -f compile_one

rm -f "$outdir"/logs/*.part
find "$outdir/ly" -name '*.ly' -print0 |
    while IFS= read -r -d '' ly; do
        [ -e "$outdir/logs/$(basename "$ly").log" ] || printf '%s\0' "$ly"
    done |
    xargs -0 -r -P "$(nproc)" -I{} bash -c 'compile_one "$1" "$2"' _ {} "$outdir" &
compiler=$!

# Report progress every 30 seconds while compiling.
while kill -0 "$compiler" 2>/dev/null; do
    done_count=$(find "$outdir/logs" -name '*.log' | wc -l)
    echo "compiled: $done_count of $(find "$outdir/ly" -name '*.ly' | wc -l) ($(date '+%H:%M:%S'))" \
        > "$outdir/progress"
    sleep 30
done
wait "$compiler"

# 3. Summary.
logs="$outdir/logs"
{
    echo "songs in library:      $total"
    echo "converted:             $(find "$outdir/ly" -name '*.ly' | wc -l)"
    echo "compiled:              $(find "$logs" -name '*.log' | wc -l)"
    echo "PDFs:                  $(find "$outdir/pdf" -name '*.pdf' | wc -l)"
    echo "LilyPond failures:     $(grep -L '^exit 0$' "$logs"/*.log 2>/dev/null | wc -l)"
    echo "with errors:           $(grep -l -P '(?<!programming )error:' "$logs"/*.log 2>/dev/null | wc -l)"
    # LilyPond-internal messages; LilyPond carries on and the PDF is still written.
    echo "with programming errors: $(grep -l 'programming error:' "$logs"/*.log 2>/dev/null | wc -l)"
    echo "with warnings:         $(grep -l 'warning:' "$logs"/*.log 2>/dev/null | wc -l)"
    echo
    echo "Most common messages:"
    cat "$logs"/*.log | grep -o "\(warning\|error\|programming error\): [^:\`'0-9]*" |
        sort | uniq -c | sort -rn | head -25
} > "$outdir/summary.txt"
echo "finished ($(date '+%H:%M:%S'))" > "$outdir/progress"
cat "$outdir/summary.txt"
