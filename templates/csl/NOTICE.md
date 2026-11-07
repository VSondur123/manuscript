# Vendored CSL citation styles

These files are unmodified copies of styles from the official Citation Style Language repository.

- Source: https://github.com/citation-style-language/styles
- Commit: `af0aea3fffd44fe798cce9285598d0d5cf62ef23` (committed 2026-11-06T14:28:28Z)
- Downloaded: 2026-11-07 from `https://raw.githubusercontent.com/citation-style-language/styles/af0aea3fffd44fe798cce9285598d0d5cf62ef23/<file>`
- License: Creative Commons Attribution-ShareAlike 3.0 Unported (https://creativecommons.org/licenses/by-sa/3.0/).
  Each file carries its own `<rights>` element and author credits; keep them intact. Redistribution of modified
  styles must stay under the same license.

| `citation_style` | File | Style (as titled in the file) |
|---|---|---|
| `apa7` | `apa.csl` | APA Style 7th edition |
| `harvard` | `harvard-cite-them-right.csl` | Cite Them Right 12th edition (author-date/Harvard) |
| `mla9` | `modern-language-association.csl` | MLA Handbook 9th edition (in-text citations) |
| `chicago-author-date` | `chicago-author-date.csl` | Chicago Manual of Style 18th edition (author-date) |
| `chicago-notes` | `chicago-notes-bibliography.csl` | Chicago Manual of Style 18th edition (notes and bibliography) |
| `vancouver` | `nlm-citation-sequence-brackets.csl` | NLM/Vancouver: Citing Medicine 2nd edition (citation-sequence, brackets) |

Word (.docx) export only (`scripts/md_to_docx.py`): the BibTeX-path styles have no LaTeX-free equivalent, so the DOCX uses these official files
(same commit, same download URL pattern, unmodified, all independent styles):

| `citation_style` | File | Style (as titled in the file) |
|---|---|---|
| `numeric` (default) | `elsevier-vancouver.csl` | Elsevier - NLM/Vancouver (citation-sequence) |
| `author-year` | `elsevier-harvard.csl` | Elsevier (author-date/Harvard, with titles) |
| `ieee` | `ieee.csl` | IEEE Reference Guide version 11.29.2023 |

These three approximate, but are not identical to, natbib `plainnat`/`IEEEtran` output in the PDF. LaTeX builds do not use them.

All six CSL-engine styles above are independent styles (no `independent-parent` link), so pandoc never needs network access.
The repository has no plain `vancouver.csl`; the NLM "Citing Medicine" style is the Vancouver system as maintained by the
U.S. National Library of Medicine and is not tied to one publisher.
The SHA-256 of the file used for a given LaTeX build is recorded in `.ms/state.json` (`latex.inputs.csl`).
To add or update a style: download from the same repository at a pinned commit, update this file, and add one entry to
`CITATION_STYLES` in `scripts/layout.py`.
