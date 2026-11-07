# Changelog

## 0.1.1 — 2026-11-07
- `/manuscript humanize [section]`: style revision pass backed by `references/humanize.md` and report-only `scripts/style_scan.py` (sentence/paragraph-length spread, stock vocabulary, template phrases, em-dash and bold density). Not a detector bypass; no score is promised.
- Citation styles via pandoc citeproc and vendored CSL (`templates/csl/`, CC BY-SA 3.0): `apa7`, `harvard`, `mla9`, `chicago-author-date`, `chicago-notes`, `vancouver` (NLM). `numeric`, `author-year`, `ieee` stay on BibTeX. A `citation_style` in project-config now takes effect (it was ignored before); the config template no longer hard-codes `numeric`.
- Whitelisted `layout:` options in project-config (paper, font size, spacing, margins, columns, font, header, page numbers, heading numbering, caption position, table style, colour) merged by the new `scripts/layout.py`; `ms_state.py layouts` and `check-config`. Default output is byte-identical to 0.1.0-beta (golden tests).
- 10 new document types (literature-review, project-report, experiment-report, research-proposal, dissertation-proposal, system-design-document, case-study, white-paper, policy-brief, conference-paper) and 5 venue templates (acm-paper, llncs-paper, elsevier-paper, revtex-paper, preprint). Springer Nature and NeurIPS/ICML/ICLR styles are not supported (not in tectonic's bundle).
- `thesis-formal` doctype: cover page, declaration, copyright, dedication, acknowledgements, lists of figures/tables/abbreviations/symbols, lettered appendices, optional roman front-matter numbering, hash-locked logo (`ms_state.py lock-logo`).
- Optional Word output: `md_to_docx.py`, `validate_docx.py`, `ms_state.py publish --docx|--docx-only`; reports what Word cannot reproduce. Checked structurally only (no Word available).
- Fixes: `compile_latex.sh` no longer mistakes a same-second or leftover PDF for success.
- Fixes from an independent check: raw LaTeX in Markdown no longer reaches LaTeX/Word (D-017); `columns: 2` + `table_style: plain` compiles; the formal-thesis cover fits one page; map-style authors work in generic types; doctype heading alternatives widened (e.g. "Materials and Methods"); the sibling PNG of a PDF figure is hash-locked (projects approved earlier with such figures must re-approve before Word export); MLA narrative cites no longer print `Lee ()`; thesis logos must live inside the project; `compile_latex.sh` requires engine exit 0 and a PDF; `style_scan` wording no longer tells users to replace legitimate terms; Word export notes when its reference style differs from the PDF.

## 0.1.0-beta — 2026-11-06
- First beta. README gains Requirements (Claude Code, Python 3.9+, pandoc/tectonic/poppler; macOS/Linux notes), a citation-verification warning, a privacy note and a feedback section.
- Fixed stale `draft.md`/`output/` wording in the draft-preview instructions; skill description now lists only the four shipped document types.
- Manual tests M11 and M12 passed; behaviour without PDF tools and the `thesis` doctype checked by the maintainer.

## 0.1.0 — 2026-11-06 (initial)
- Skill orchestrator, 8 reference docs, 3 document types.
- Scripts: state engine with hash-enforced approvals, discovery, Markdown/BibTeX/LaTeX validators, pandoc conversion from approved snapshot, compile wrapper, PDF inspector.
- 42 automated tests; manual checklist in `tests/MANUAL_TESTS.md`.
- Known gaps: see README "Limitations". MIT LICENSE added.

### Fixes from manual testing (2026-11-06)
- Added `ms_state.py doctypes` (skill folder is outside the project dir; the model could not read `doctypes/`).
- `project-config.yaml` can override `required_sections` / `recommended_sections` / `require_abstract` (assignment beats doctype defaults).
- Plan convention: `## Approved structure` holds titles only; descriptions go in `## Section notes`.
- SKILL.md: never claim a tool is missing without script evidence (model had wrongly reported tectonic absent).

### Figures and IEEE (2026-11-06)
- `ieee-report` doctype: IEEEtran pandoc template, two-column-safe table filter, `\cite`, "Fig." abbreviation.
- Draft preview: `md_to_latex.py --preview` (watermarked, unapproved, no state change).
- `build_figures.py` (blocks + bar/line charts from specs/CSV), `csv_table.py`; figures/specs/data hash-locked by approval (D-010, D-011).

### Clean folder layout (2026-11-06)
- Visible project folder now holds only `plan.md` → `<id>-report.md` → `<id>.tex`/`<id>.pdf`. All internals moved to hidden `.ms/` (state, config, evidence, bib, figures, specs, data, validation, logs, history, approved, latex build).
- Report renamed from `draft.md` to `<id>-report.md`; figure links are `.ms/figures/...` in the report and rewritten to `figures/...` for LaTeX.
- New `ms_state.py publish` copies the final `.tex`/`.pdf` out of `.ms/latex/` at the end.
- Breaking: existing projects (state.json at project root) must be migrated manually; the `.tex` at the root is not standalone-compilable (figures/bib stay in `.ms/latex/`).
- Report now includes a generated `# References` list for review (`render_references.py`); stripped for LaTeX.
