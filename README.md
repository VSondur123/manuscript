# ManuScript

An approval-driven Claude Code skill that turns research materials (Markdown, PDFs, notes, assignment guidelines, data) into a professionally structured academic document: **plan → evidence inventory → editable Markdown → approved Markdown → LaTeX → inspected PDF**.

The user controls the content. ManuScript controls the workflow, consistency, validation and production. It is not a free-form writing assistant: it has explicit stages, persistent state (`.ms/state.json`), deterministic validators, hash-enforced approval gates and a rendered-PDF check.

## Requirements
- **Claude Code** (CLI, desktop or IDE). ManuScript is a Claude Code skill and does not run on its own.
- **Python 3.9+** (standard library only, no `pip install`).
- **For LaTeX/PDF output:** `pandoc`, a LaTeX engine (`tectonic` recommended) and poppler.
  - macOS: `brew install tectonic pandoc poppler`
  - Linux: install `pandoc` and `poppler-utils` from your package manager, plus `tectonic` (see tectonic-typesetting.github.io) or a TeX Live install (`xelatex`/`latexmk`).
  - Windows: untested. Use WSL and follow the Linux steps.
- Without the PDF tools, discovery, planning, drafting and Markdown validation still work; PDF stages report what is missing.
- **Verify citations yourself.** ManuScript checks that citations resolve to your bibliography, not that the sources exist or say what the draft claims. Do not submit graded or published work without checking every reference.

## Privacy
Your materials stay on your machine, but Claude Code sends the files it reads to Anthropic's API as part of normal use (see your Claude Code data-usage settings). Do not use ManuScript on confidential or unpublished material you are not allowed to share with a cloud AI service.

## How it works
- `SKILL.md` is the orchestrator; `references/*.md` hold per-stage guidance; `doctypes/*.yaml` define document types; `templates/` holds config and LaTeX defaults; `scripts/` holds deterministic tools (Python 3.9+ stdlib only, plus pandoc / tectonic / poppler CLIs).
- Each document is a project in `manuscript/<project-id>/` (several per repository are fine): only three things are visible: `plan.md` → (on `APPROVE PLAN`) `<project-id>-report.md` → (on `APPROVE MARKDOWN`) `<project-id>.tex` + `.pdf`. All internals (state, config, evidence inventory, bibliography, figures, validation, logs, backups, approved snapshots, LaTeX build) live in the hidden `.ms/` folder.
- Approval gates: the user must type exactly `APPROVE PLAN` / `APPROVE MARKDOWN`. Approval stores a SHA-256 hash and a read-only snapshot. Any later edit makes the approval stale; `md_to_latex.py` converts only the approved snapshot and refuses otherwise.
- Every invocation compares `.ms/state.json` with the files (hashes). Files win; external edits are reported, never overwritten. Drafts are backed up to `.ms/history/` before ManuScript edits them.

## Install (choose one; nothing is installed automatically)
Project-level (this repository only):
```bash
mkdir -p <your-repo>/.claude/skills
git clone https://github.com/VSondur123/manuscript.git <your-repo>/.claude/skills/manuscript          # or: ln -s / cp -R
```
User-level (all projects):
```bash
mkdir -p ~/.claude/skills
git clone https://github.com/VSondur123/manuscript.git ~/.claude/skills/manuscript                    # or: ln -s / cp -R
# update later: git -C ~/.claude/skills/manuscript pull
```
Edits to installed skills are picked up live; if the top-level `skills` directory is new, run `/reload-skills`. Restart not required.

## Quick start
1. Install the skill (below) and the tools in Requirements.
2. Put your sources (notes, PDFs, assignment brief) in a folder, `cd` into it, start Claude Code.
3. Run `/manuscript`. Give it a project id and document type when asked.
4. Review `manuscript/<id>/plan.md`, edit if needed, then type `APPROVE PLAN`.
5. Review `manuscript/<id>/<id>-report.md`, ask for changes, then type `APPROVE MARKDOWN`.
6. Get `manuscript/<id>/<id>.tex` and `<id>.pdf`.

## Use
Open Claude Code in the folder containing your materials:
- `/manuscript` — start or resume
- `/manuscript continue` · `status` · `validate` · `review` (arguments are passed to the skill; natural language also works)
Typical session: discovery → plan (edit, then `APPROVE PLAN`) → evidence → draft (edit freely or ask for changes) → validation report → `APPROVE MARKDOWN` → LaTeX → PDF → QA → `manuscript/<id>/<id>.tex` + `<id>.pdf` (via `ms_state.py publish`).
Ask for a **draft preview** at any time for a watermarked PDF of the unapproved draft (not a deliverable).
Resume in a new session by running `/manuscript` again in the same directory.

## Figures, diagrams, charts
The report ends with a readable `# References` list (generated from `.ms/references.bib` by `render_references.py`) so reviewers can check sources; it is dropped for LaTeX, where BibTeX builds the bibliography.

Block/workflow diagrams and bar/line charts are built from JSON specs (`.ms/figures-src/`) into vector PDFs by `build_figures.py` (TikZ/pgfplots, no extra dependencies); CSV subsets become captioned tables via `csv_table.py`. Figure files, specs and input CSVs are hash-locked by the Markdown approval. See `references/figures.md`.

## Document types
Shipped: `research-report`, `technical-report`, `thesis`, `ieee-report` (IEEEtran conference layout, two columns, `\cite` numeric IEEE style). Add one by creating `doctypes/<name>.yaml` (see `references/doctypes.md`). Not yet defined: literature review, experiment report, system design document, research proposal.

## Dependencies
Required: Python ≥ 3.9, git (optional). For LaTeX/PDF: `pandoc`, a LaTeX engine (`tectonic` recommended; `latexmk`/`xelatex`/`pdflatex` auto-detected), poppler (`pdftotext`, `pdfinfo`, `pdftoppm`, `pdffonts`). macOS: `brew install tectonic pandoc poppler`. Without them, discovery, planning, drafting and Markdown validation still work; PDF stages report the missing tool.

## Tests
```bash
cd tests && python3 -m unittest discover -v
```
Pipeline tests are skipped when pandoc/tectonic/poppler are missing. Claude-Code-specific behaviour is covered by `tests/MANUAL_TESTS.md`.

## Limitations (see also CHANGELOG)
- Approval phrases are enforced by scripts, but nothing technically stops a model from passing the phrase without the user typing it; the SKILL.md rule is the safeguard. A hook-based enforcement is a possible future addition.
- Bibliography: BibTeX/natbib only (biblatex/biber not supported by the default templates). Citation *existence* is not verified (no DOI lookup).
- Markdown word counts are approximate; page limits are measured only from the PDF.
- PDF inspection is heuristic (margins, edge clipping, blank pages, unresolved refs, fonts); caption/figure placement need visual review of the rendered PNGs.
- DOCX extraction is text-only; scanned PDFs are not OCR'd; XLSX is listed but not read.
- `thesis` template and institutional template packs are basic/untested on real university templates.
- Markdown subset: figures/tables labels via pandoc attributes; no pandoc-crossref.

## Beta feedback
This is a beta. When reporting a problem, please include: the stage (`/manuscript status`), the command or step that failed, its error output, and the relevant file in `<project>/.ms/logs/`. Do not attach confidential source documents. Open an issue on this repository's GitHub Issues page.

## License
MIT. See `LICENSE`.
