# ManuScript Decision Log

Status values: Proposed, Approved, Rejected, Superseded.

## D-001 — Skill packaging
- **Date:** 2026-11-06
- **Context:** Claude Code 2.1.311 discovers skills at `.claude/skills/<name>/SKILL.md` (project) and `~/.claude/skills/<name>/SKILL.md` (user); plugins namespace the command (`/plugin:skill`).
- **Alternatives:** (A) standalone skill folder; (B) plugin; (C) standalone, plugin-ready later.
- **Recommendation:** C.
- **Decision:** C — standalone skill folder, laid out so a plugin manifest can be added later.
- **Reasoning:** Keeps the `/manuscript` command un-namespaced and installation to a copy or symlink; costs nothing to stay plugin-compatible.
- **Consequences:** Install by copying/symlinking into a skills directory. No global changes are made by the project.
- **Status:** Approved

## D-002 — Markdown to LaTeX conversion
- **Date:** 2026-11-06
- **Context:** Needs tables, math, figures, citations from approved Markdown.
- **Alternatives:** (A) Pandoc plus templates; (B) pure-Python converter; (C) Pandoc with Python fallback.
- **Recommendation:** A.
- **Decision:** A — Pandoc plus LaTeX templates.
- **Reasoning:** Mature, high fidelity, avoids reimplementing a Markdown parser.
- **Consequences:** Pandoc is a required dependency for LaTeX generation. Scripts must detect it and report clearly when it is missing.
- **Status:** Approved

## D-003 — System tooling for LaTeX and PDF QA
- **Date:** 2026-11-06
- **Context:** No pandoc, LaTeX engine, or poppler was installed when first checked (2026-11-06); they have since been installed.
- **Alternatives:** (A) tectonic + pandoc + poppler via Homebrew; (B) BasicTeX/MacTeX; (C) install nothing.
- **Recommendation:** A.
- **Decision:** A — tectonic, pandoc, poppler. Installation is still performed only when explicitly confirmed at install time.
- **Reasoning:** Small footprint versus MacTeX (~5 GB).
- **Consequences:** Tectonic does not run biber, so bibliography uses BibTeX styles (natbib). `compile_latex.sh` should still support latexmk/xelatex/pdflatex/biber when present.
- **Status:** Approved (installed 2026-11-06)

## D-004 — Python dependencies
- **Date:** 2026-11-06
- **Context:** System Python is 3.9.6 with no third-party libraries.
- **Alternatives:** (A) stdlib only, optional extras; (B) require PyYAML/pypdf/pytest etc.
- **Recommendation:** A.
- **Decision:** A — standard library only for core scripts; tests use `unittest`; PDF text/rendering via poppler CLI.
- **Reasoning:** Zero pip install friction and portable.
- **Consequences:** Python 3.9-compatible syntax only. Configuration and state use JSON, or a restricted YAML subset parsed by our own code.
- **Status:** Approved

## D-005 to D-009 — Architecture proposals
- **Date:** 2026-11-06
- **Decision:** All approved as proposed.
  - D-005 Per-document workspace `manuscript/<project-id>/`, multiple projects per repository.
  - D-006 Approval by exact phrase `APPROVE MARKDOWN`; SHA-256 hash and snapshot in `approved/`; later edits invalidate approval.
  - D-007 `state.json` with the brief's stage list, verified against file hashes every invocation; files win over stale state.
  - D-008 One definition file per document type in `doctypes/`.
  - D-009 Previous draft copied to `.ms/history/` before any ManuScript edit.
- **Status:** Approved

## D-010 — Diagram and chart generation
- **Date:** 2026-11-06
- **Context:** Reports need workflow/block diagrams, charts and CSV-derived tables. v1 only embedded existing images.
- **Alternatives:** (A) restricted JSON specs rendered to TikZ/pgfplots by a stdlib Python script; (B) install matplotlib + Graphviz; (C) model writes freehand TikZ per figure.
- **Recommendation:** A.
- **Decision:** A. Specs live in `.ms/figures-src/*.json`, `build_figures.py` renders `figures/<name>.pdf` + `.png` and a `figures/manifest.json` with hashes/provenance. `csv_table.py` turns CSV subsets into captioned Markdown tables with provenance comments.
- **Reasoning:** No new dependencies, vector output, deterministic and reviewable.
- **Consequences:** Only the supported diagram types (blocks/lanes/arrows) and chart kinds (bar, line) exist; other figures must be supplied as images. Spec uses JSON because the built-in YAML subset has no list-of-maps.
- **Status:** Approved

## D-011 — Approval covers figures
- **Date:** 2026-11-06
- **Decision:** Markdown approval records SHA-256 hashes of every referenced local figure, its spec and its input data files. Any change makes the approval stale (same as editing the text).
- **Status:** Approved

## D-012 — Humanize as an argument, not a separate skill
- **Date:** 2026-11-07
- **Context:** Users want `/manuscript humanize`. Multi-skill repos (e.g. BMAD) give each command its own `SKILL.md`.
- **Alternatives:** (A) argument + reference doc + script inside the one skill; (B) separate `manuscript-humanize` skill folder.
- **Decision:** A.
- **Reasoning:** One state machine and one set of approval/backup rules; humanize edits the same report file and must respect them. A second skill would duplicate those rules or bypass them. Reference files already give progressive loading.
- **Consequences:** `/manuscript humanize` works; `/manuscript-humanize` would need a thin wrapper skill that delegates to this one.
- **Status:** Approved

## D-013 — Citation styles via CSL, not per-style BibTeX templates
- **Date:** 2026-11-07
- **Alternatives:** (A) pandoc `--citeproc` with vendored official CSL files; (B) a BibTeX `.bst` per style; (C) biblatex/biber.
- **Decision:** A for apa7, harvard, mla9, chicago, vancouver; the default numeric/author-year/ieee path stays on BibTeX so existing output is unchanged.
- **Reasoning:** Tectonic does not run biber; CSL files are official and cover the styles users are asked for. `vancouver` maps to NLM "Citing Medicine" because the CSL repo has no plain vancouver file.
- **Consequences:** CSL files are CC BY-SA 3.0 (recorded in `templates/csl/NOTICE.md`); CSL hash is stored in state; CSL is rejected for ieee-report and custom templates without `$csl-refs$`; MLA narrative cites need a locator.
- **Status:** Approved

## D-014 — Whitelisted layout options with one merge point
- **Date:** 2026-11-07
- **Decision:** Layout options are an enumerated whitelist merged in `scripts/layout.py` (built-in < doctype < config). Values never reach LaTeX as free text. Generated defaults/header files are hashed into state. Options a font or template cannot compile were cut (fontspec-by-family-name fonts).
- **Status:** Approved

## D-015 — thesis-formal is a separate doctype
- **Date:** 2026-11-07
- **Alternatives:** (A) new doctype; (B) `frontmatter: true` switch on `thesis`.
- **Decision:** A. The doctype is recorded in state and reviewed at plan time; the default `thesis` output stays byte-identical. The logo is hash-locked like a figure (extends D-011).
- **Status:** Approved

## D-016 — DOCX is an optional export, not a stage
- **Date:** 2026-11-07
- **Decision:** `md_to_docx.py` converts the approved snapshot only, adds no state stage, writes `.ms/docx/<id>.docx` and is copied to the visible folder only by `publish --docx`/`--docx-only`. The visible-files rule allows `<id>.docx` on request. Venue and thesis-formal typesetting is not reproduced in Word and every export says so. Output is validated structurally only.
- **Status:** Approved

## D-017 — Raw LaTeX in Markdown is not passed through
- **Date:** 2026-11-07
- **Context:** Independent check showed `\input{/etc/passwd}` in the Markdown reached LaTeX (pre-existing).
- **Decision:** Read Markdown as `markdown-raw_tex`; warn in validation. Trade-off: users can no longer embed raw LaTeX in the report; use config options instead.
- **Consequences:** a `raw-latex-ignored` warning is shown; math must use `$`/`$$`. Verified: the `\input{/etc/passwd}` draft compiles without reading the file.
- **Status:** Approved
