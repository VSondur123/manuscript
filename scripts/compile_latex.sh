#!/usr/bin/env bash
# Compile a .tex file to PDF with the best available engine and summarise the log.
# Usage: compile_latex.sh <file.tex> [engine]   engine: auto (default) | latexmk | tectonic | xelatex | pdflatex | lualatex
# Output: PDF next to the .tex; full log in <tex dir>/../logs/compile.log. Exit: 0 ok, 1 compile failed, 2 usage/no engine.
set -u
tex="${1:-}"; engine="${2:-auto}"
[ -f "$tex" ] || { echo "usage: compile_latex.sh <file.tex> [engine]" >&2; exit 2; }
dir="$(cd "$(dirname "$tex")" && pwd)"; name="$(basename "$tex" .tex)"
logdir="$dir/../logs"; mkdir -p "$logdir"; log="$logdir/compile.log"

have() { command -v "$1" >/dev/null 2>&1; }
if [ "$engine" = auto ]; then
  for e in latexmk tectonic xelatex pdflatex lualatex; do have "$e" && { engine="$e"; break; }; done
fi
have "$engine" 2>/dev/null || { echo "ERROR: no LaTeX engine available (install tectonic or a TeX distribution)" >&2; exit 2; }

cd "$dir" || exit 2
rm -f "$dir/$name.pdf"   # build output only: a leftover PDF must never count as success
engine_rc=0
{
  echo "# engine: $engine   started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  (
  case "$engine" in
    latexmk)  latexmk -pdf -interaction=nonstopmode -halt-on-error "$name.tex" ;;
    tectonic) tectonic -X compile --keep-logs "$name.tex" 2>&1 || tectonic "$name.tex" 2>&1 ;;
    *)        # classic engine: tex, bibtex, tex, tex
              "$engine" -interaction=nonstopmode -halt-on-error "$name.tex" &&
              { have bibtex && [ -f "$name.aux" ] && grep -q '\\bibdata' "$name.aux" && bibtex "$name" || true; } &&
              "$engine" -interaction=nonstopmode -halt-on-error "$name.tex" &&
              "$engine" -interaction=nonstopmode -halt-on-error "$name.tex" ;;
  esac
  ) ; engine_rc=$?
  echo "# exit: $engine_rc"
  echo "$engine_rc" >"$dir/.engine_rc.$$"
} >"$log" 2>&1
engine_rc="$(cat "$dir/.engine_rc.$$" 2>/dev/null || echo 1)"; rm -f "$dir/.engine_rc.$$"
rc=0
# success needs BOTH a zero engine exit status and a non-empty fresh PDF
{ [ "$engine_rc" = 0 ] && [ -s "$dir/$name.pdf" ]; } || rc=1

echo "engine: $engine   log: $log"
if [ $rc -eq 0 ]; then echo "PDF: $dir/$name.pdf"; else echo "COMPILE FAILED"; fi
grep -iE "^!|error|undefined (citation|reference)|Citation .* undefined|Reference .* undefined|Label .* multiply|LaTeX Warning: There were|File .* not found|Overfull .hbox|Underfull .hbox" "$log" | sort | uniq -c | sort -rn | head -25
exit $rc
