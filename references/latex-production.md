# LaTeX production

- `md_to_latex.py` converts the **approved snapshot** with pandoc using `templates/latex/<article|book>.yaml` (document class, geometry, natbib options). It refuses if approval is missing/stale or the snapshot was altered. Output: `latex/<id>.tex`, `latex/references.bib`, copied figures.
- Institutional template: set `template:` in `project-config.yaml` (a pandoc LaTeX template) or pass `--template-file`. If the institution supplies a `.cls`, ask the user how to integrate before proceeding.
- Allowed mechanical changes (always logged): drop trailing empty References heading; `[Figure](#fig-x)` → `Figure~\ref{fig-x}`. Everything else is content and must not change.
- Bibliography: natbib + BibTeX (`numbers` for numeric, `authoryear` for author-year). Tectonic does not run biber, so biblatex is not supported by the default templates.
- `validate_latex.py` before compiling: figure files, labels/refs, cite keys, bibliography file, environments, braces, placeholders.
- `compile_latex.sh` picks latexmk → tectonic → xelatex → pdflatex → lualatex (first available) and writes `.ms/logs/compile.log`. Report actionable errors from the log. Fix via markup/template; do not edit approved wording. If the fix requires a content change: return to Markdown and re-approve.
- The `.tex` is editable by the user, but the Markdown remains authoritative; hand edits to `.tex` are lost on regeneration — say so.
