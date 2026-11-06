# Evidence management

Traceability chain: **Source → Evidence → Claim → Document section → Citation**.

## `evidence-inventory.md` format
Two tables (plain Markdown so the user can edit them).

Sources:
| ID | Location | Type | Primary/Secondary | Topic / sections | Citation key | Limitations |
|----|----------|------|-------------------|------------------|--------------|-------------|

Evidence items:
| ID | Source | Extract / finding (exact figures, page/line) | Kind | Supports claim | Section | Status |
|----|--------|-----------------------------------------------|------|----------------|---------|--------|
Kind ∈ observed | source-derived | interpretation | recommendation. Status ∈ verified | needs-check | conflict | gap.

Plus a **Conflicts** list (both positions with locations; ask the user) and a **Gaps** list (claims the plan needs that no source supports).

## Rules
- Record only what you actually read. Quote or tightly paraphrase; note page/section where known.
- Citation metadata only from the source itself (title page, DOI line, BibTeX the user gave). Missing metadata stays missing — put a note in the inventory, do not guess. Add BibTeX entries only when verified; `validate_references.py` rejects placeholder values.
- Do not silently reconcile conflicting numbers/dates/definitions.
- The user may inspect and edit the inventory at any time; re-read it before drafting and after changes (`sync`).
