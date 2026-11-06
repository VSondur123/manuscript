# Figures, diagrams, charts and CSV tables

Figures are built from small editable **spec files** so they are reproducible, reviewable and covered by the approval gate. Only the types below exist; anything else must be supplied as an image file (never fabricate one).

## Workflow
1. In the **plan**, propose figures/tables per section: purpose, type, data source (file + columns). The user edits this list with the TOC.
2. Write specs to `.ms/figures-src/<name>.json`; run `python3 ${CLAUDE_SKILL_DIR}/scripts/build_figures.py` (`--only name`, `--check` for freshness). It writes `figures/<name>.pdf` (used by LaTeX), `figures/<name>.png` and `figures/manifest.json`.
3. **Look at the PNG** (Read tool). Check labels, arrow directions, overlap, legibility at column width, and that every box/number is traceable to a source. Iterate on the spec.
4. Include it in `<id>-report.md`: `![Caption](.ms/figures/<name>.pdf){#fig-<name>}` and refer to it: `[Figure](#fig-<name>)`. For preview or non-PDF consumers the same name with `.png` exists.
5. Any change to a spec, its CSV, or the image after `APPROVE MARKDOWN` makes the approval stale (the approval records their SHA-256 hashes).

## Block / workflow diagram (`"type": "blocks"`)
```json
{"type":"blocks","caption":"...","orientation":"vertical","width_cm":8.8,
 "lanes":[{"label":"BMAD","nodes":[{"id":"b1","text":"Analyst: brief","style":"start"},
                                   {"id":"b2","text":"Owner approval","style":"gate"}]},
          {"label":"Spec Kit","nodes":[{"id":"s1","text":"/specify"}]}],
 "edges":[["b1","b2"],{"from":"s1","to":"b2","label":"compare","style":"dashed"}]}
```
- Lanes are columns (`vertical`, default, fits one IEEE column) or rows (`horizontal`). Nodes stack/flow in list order; set `"row": N` to align nodes across lanes.
- Styles: `default`, `start`, `end`, `gate` (approval/decision), `artifact` (dashed). Edges are `[from, to, optional label]` or objects; arrows join sides when nodes share a row/lane, else straight lines — align rows to avoid crossings.
- Node text must come from sources (e.g. real phase/command names). Use `\n` for line breaks. Keep text short (≈ 25 characters per line).

## Chart (`"type": "chart"`, `"kind": "bar" | "line"`)
```json
{"type":"chart","kind":"bar","ylabel":"Count","caption":"...",
 "source":{"csv":"../../shared/results.csv","x":"metric","series":["bmad","speckit"],"rows":"1-5"}}
```
or inline `"data":{"x":[...],"series":[{"name":"...","values":[...]}]}` (values must come from a cited source). CSV paths are relative to the project directory. Non-numeric values or missing columns are errors; nothing is coerced or invented. Bar charts start at 0 unless `ymin` is set.

## CSV snippet as a table
`python3 ${CLAUDE_SKILL_DIR}/scripts/csv_table.py --csv FILE --columns a,b --rows 1-5 --caption "..." --label tbl-x` prints a pipe table, `Table: caption {#tbl-x}` and a `<!-- source: ... sha256=... -->` provenance comment. Values are copied verbatim; long cells are truncated at 60 characters (use `--max-cell`). Paste into `<id>-report.md`; note the CSV in the evidence inventory.

## Limits
Two-column IEEE: diagrams are column-width. Large flow charts (more than ~8 nodes per lane) should be split. No automatic graph layout; no pie/scatter charts yet; XLSX is not read (export to CSV first).
