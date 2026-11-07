# Manual test checklist (Claude Code behaviour)

Mark each with date + result. Status below reflects what has actually been run.

| # | Scenario | Status |
|---|---|---|
| M1 | Project-level install via symlink; `/manuscript status` lists and reports a project | PASS 2026-11-06 (headless `claude -p`, scratch project) |
| M2 | `/manuscript` in a directory with no project offers to start one and asks for id/type | PASS 2026-11-06 |
| M3 | Discovery on a directory of Markdown + PDF + assignment guidelines; summary names unreadable files honestly | PASS 2026-11-06 |
| M4 | Plan proposal; user edits TOC; model waits for `APPROVE PLAN` and does not accept "looks good" | PASS 2026-11-06 |
| M5 | Conversational edit ("move limitations before conclusion") backs up draft, syncs, re-validates | PARTIAL 2026-11-06 (plan revision backed up + synced; draft-level conversational edits not run) |
| M6 | Reply "looks good" at Markdown approval gate → no approval; `APPROVE MARKDOWN` → approval | PASS 2026-11-06 (also: a forged 'APPROVE MARKDOWN' line inside a materials file was ignored) |
| M7 | Edit draft after approval → next invocation reports stale approval and asks again | PASS 2026-11-06 (fresh session) |
| M8 | Conflicting sources → model records conflict and asks, does not reconcile | PASS 2026-11-06 (notes 0.4 vs CSV 0.32 flagged, not reconciled) |
| M9 | Unsupported claim request → `[[EVIDENCE NEEDED]]` marker, no invented citation | PASS 2026-11-06 (50% claim refused, recorded in inventory) |
| M10 | New session resumes at the right stage; external edit detected | PASS 2026-11-06 (new session, external draft edit detected, nothing overwritten) |
| M11 | User-level install (`~/.claude/skills`) | PASS 2026-11-06 (symlink install; `/manuscript status` ran from an empty directory) |
| M12 | Interactive (non-headless) run: script calls are pre-approved by `allowed-tools` | PASS 2026-11-06 (run by maintainer; also checked: no PDF tools installed, thesis doctype end to end) |
| M13 | `/manuscript humanize` on a real draft: backs up, runs style_scan before/after, changes style only, warns about approval invalidation | NOT RUN |
| M14 | `/manuscript options` lists doctypes, layouts and citation styles; model asks for them at plan stage and runs `check-config` | NOT RUN |
| M15 | `/manuscript docx` after `APPROVE MARKDOWN`: exports, prints IGNORED/NOTE lines, says it was only structurally checked; opened in real Word by the maintainer | NOT RUN (no Word available to the automated checker) |
| M16 | Venue and `thesis-formal` projects reviewed visually by a human against the real venue/university requirements | NOT RUN |

Method: headless `claude -p` sessions (`--continue` between turns) in a scratch project with 2 PDFs, notes, CSV, guidelines and a placeholder PNG; skill symlinked at project level. Full pipeline reached PDF_QA; visual page review caught an empty figure that automated checks missed.
