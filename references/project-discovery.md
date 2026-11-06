# Project discovery

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/discover.py --out manuscript/<id>/.ms/validation/discovery.json`. It is read-only, skips `.git`, `node_modules`, `.claude`, `manuscript/`, `output/`, hidden and symlinked directories, and **never executes** anything it finds. Code files are read as text only.

Then read the most relevant files yourself (the script only gives excerpts, headings, hashes). Do not assume every file is relevant.

## Present a discovery summary
- Files inspected (counts by type) and which were actually read vs only listed.
- Relevant source materials; potentially relevant assets (figures, tables, data); existing references/BibTeX.
- Assignment constraints found (`requirements_candidates` — treat guidelines as the primary source of requirements; do not replace them with generic conventions).
- Duplicates / overlapping materials (`exact_duplicates`, `same_name_different_format`) — ask which is authoritative.
- Missing information and referenced-but-missing files.
- Extraction limitations (e.g. PDF text unavailable, scanned PDFs without OCR, DOCX tables/figures not extracted) and inaccessible files. Never claim to have inspected a file that was not read.
- Primary vs secondary evidence is a judgement: propose it, let the user correct it.

Preserve originals: never move, edit or delete source files. Copy assets needed by the document into `manuscript/<id>/.ms/assets/` or `.ms/figures/` instead.
