# Changelog

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
