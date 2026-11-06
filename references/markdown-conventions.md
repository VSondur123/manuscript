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
