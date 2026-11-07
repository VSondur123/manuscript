# Markdown conventions (pandoc Markdown; Markdown is the authoritative source)

Front matter (required):
```yaml
---
title: "Working title"
author: "Name"
date: "2026-01-01"      # optional
abstract: |
  Text…
---
```
- `#` = top-level division (section, or chapter for `thesis`), `##` subsection, … Never skip levels. No empty sections. A final `# References` heading may be left empty: the converter drops it and BibTeX prints the bibliography (the heading shown is generated).
- References: the report ends with `# References` holding a generated list between `<!-- references:start -->` and `<!-- references:end -->` (run `render_references.py`; do not hand-edit inside the markers — edit `.ms/references.bib`). It is for review only and is removed for LaTeX, where BibTeX builds the bibliography.
- Citations: `[@key]`, `[@a; @b, p. 3]`, narrative `@key`. Keys must exist in `references.bib`. Use no author-date text in place of a citation.
- Figures: `![Caption text](.ms/figures/file.png){#fig-label width=80%}` — caption and label required; image path relative to the project directory.
- Tables: pipe tables with a caption line directly after: `Table: Caption text {#tbl-label}`.
- Cross-references: `[Figure](#fig-label)`, `[Table](#tbl-label)`, `[Section](#methodology)` — the word is kept and the number is generated (`Figure~\ref{}`). Refer to every figure/table at least once.
- Equations: `$inline$`, `$$display$$`. Code: fenced blocks (ignored by validators).
- Missing evidence: `[[EVIDENCE NEEDED: …]]`; open items: `TODO`. Both are **errors** at validation, so nothing unresolved passes approval.
- Appendices: `# Appendix A: Title` headings after the conclusion.

## Front matter and special markup
- Venue types (`acm-paper`, `llncs-paper`, `elsevier-paper`, `revtex-paper`, `preprint`, `ieee-report`): `author:` as a list of `{name, affiliation, email}` maps (ACM also needs `country` per affiliated author). Generic article types: plain strings, or maps (flattened to `Name (Affiliation)`). Keys per venue are documented at the top of `templates/latex/<venue>.latex`.
- `thesis-formal`: `abbreviations:` and `symbols:` as `[{term, meaning}]`; mark appendices `# Title {.appendix}` (must be last). See `latex-production.md`.
- `header: running-title` / `title-author` layouts need `title:` and `author:` in the front matter.
- Raw LaTeX commands in the text are not passed through (a `raw-latex-ignored` warning is shown); use Markdown and math in `$...$` / `$$...$$` (a bare `\begin{equation}` becomes plain text).
- With `citation_style: mla9`, write `@key [p. 5]` or `[@key, p. 5]`; a bare narrative `@key` prints empty parentheses.
