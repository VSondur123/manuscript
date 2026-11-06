# Quality assurance

## Markdown (`validate_markdown.py`)
Errors block approval: missing title/abstract (if required), heading skips, empty sections, missing required sections, missing figure files/captions, tables without captions, broken internal links, citations missing from the bibliography, unresolved placeholders, word-limit violations. Warnings: unreferenced figures/tables, unused bib entries, plan/draft structure differences. Confirmations: section order differs from plan; page limits (not measurable pre-PDF). Reports: `validation/markdown-validation.{md,json}`.
Things scripts cannot judge (do these yourself and tell the user): unsupported claims, tone, argument quality, whether evidence supports each claim (check against `evidence-inventory.md`).

## References (`validate_references.py refs.bib --cited-in <id>-report.md`)
Required fields per entry type, duplicate keys, placeholder values (Unknown/TBD), odd years, DOI format. It cannot verify that a reference exists — that is the user's responsibility; say so.

## PDF (`inspect_pdf.py`)
Page count/size, fonts, blank pages, unresolved `??`/`(author?)`, ink at page edges, narrow margins, orphaned-heading heuristic, last-page length; renders PNGs. **Then view the PNGs** (Read tool on `validation/pages/page-N.png`) for figure/caption placement, table overflow, title page, headers/footers. Report what you looked at and what you could not check. Fix layout via template/markup; recompile; re-inspect.
