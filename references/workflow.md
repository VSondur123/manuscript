# Workflow and state transitions

State lives in `manuscript/<id>/.ms/state.json`; the file system is the source of truth. Every invocation: `status` → `verify` → reconcile → resume.

## Stage definitions and exit criteria
1. **INITIALISED** — workspace created by `ms_state.py init`. Copy `templates/project-config.yaml` to `project-config.yaml` and fill it with the user. Exit: config exists.
2. **DISCOVERY_IN_PROGRESS → DISCOVERY_COMPLETE** — see `project-discovery.md`. Exit: user has seen the discovery summary and confirmed which materials are relevant.
3. **PLAN_PENDING_APPROVAL** — write `plan.md`: document type, working title, purpose, audience, objective, research questions, scope/exclusions, constraints (from assignment guidelines first), citation style, limits, required figures/tables, then `## Approved structure`: a bullet list containing ONLY section titles, one bullet per heading, nested with 2 spaces = heading hierarchy (the validator treats every bullet as a heading; include Abstract only if it is a body heading). Put each section's purpose, expected evidence and page allocation in a separate `## Section notes` table or list. Ask the user to modify or reply `APPROVE PLAN`.
4. **PLAN_APPROVED** (entered only by `approve-plan`) — editing `plan.md` afterwards makes the approval stale; re-approve.
5. **EVIDENCE_ANALYSIS** — build/inspect `.ms/evidence-inventory.md` (`evidence-management.md`). Exit: every planned section has identified evidence or an explicit gap list the user has seen.
6. **MARKDOWN_DRAFTING** — write `<id>-report.md`. `ms_state.py backup <id>-report.md` before every later edit; `sync` after.
7. **MARKDOWN_VALIDATION** — `render_references.py` (so the reviewer sees the full reference list in the report), then `validate_markdown.py`; fix errors; list warnings/suggestions/confirmations to the user.
8. **MARKDOWN_PENDING_APPROVAL** — present the validation report and ask for exactly `APPROVE MARKDOWN`. Requested changes → return to MARKDOWN_DRAFTING.
9. **MARKDOWN_APPROVED** (only via `approve-markdown`) — snapshot written to `.ms/approved/draft-approved-vN.md` (read-only, hash recorded).
10. **LATEX_GENERATION** — `md_to_latex.py`. Content is never altered; allowed mechanical changes are logged in `.ms/logs/latex-generation.log`.
11. **LATEX_VALIDATION** — `validate_latex.py`.
12. **PDF_GENERATION** — `compile_latex.sh .ms/latex/<id>.tex`; show actionable errors from the log.
13. **PDF_QA** — `inspect_pdf.py`, view rendered pages, fix layout (markup/template only), recompile. Unfixable issues are reported.
14. **COMPLETED** — run `ms_state.py publish` (copies `<id>.tex` and `<id>.pdf` to the visible folder), write `.ms/validation/final-report.md` (what was approved, files, checks run, outstanding issues).

## Recovery
- Missing/corrupt `.ms/state.json`: explain; reconstruct from files only with user consent (init a new project and `sync`), never delete files.
- `verify` drift: report which artifact changed; `sync` accepts the user's edit. Draft change after approval → approval is stale → `verify --fix` and re-approval.
- Never overwrite `.ms/approved/` snapshots; new approvals get a new version number.

## Multiple projects
Each project is independent under `manuscript/<id>/`. Always pass the project id when more than one exists.
