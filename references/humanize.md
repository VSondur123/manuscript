# Humanize: make the draft read like the author, not a model

Invoked as `/manuscript humanize [project-id] [section]`. This is a revision pass on `<id>-report.md`, not a detector-evasion tool. The goal is prose that carries the author's own material and voice. Detectors measure predictability, not authorship, and give false positives (notably on non-native writers), so no pass can guarantee any detector score. Never promise one.

## Boundaries
- Change style only. Do not change claims, numbers, citations (`[@key]`), cross-references, figures, tables, equations, headings (the approved structure), or `[[EVIDENCE NEEDED]]` markers.
- Never add facts, anecdotes, data or opinions the user did not supply. If a passage is generic because the evidence is thin, say so and ask for the user's own material (a measurement, an observation, a decision they made, what surprised them).
- Never use evasion tricks: homoglyphs, invisible characters, injected typos, or synonym-swapping that alters meaning or terminology. Keep source terminology exactly where accuracy depends on it.
- If the draft is past `MARKDOWN_PENDING_APPROVAL`, warn that edits invalidate approval (`verify --fix`, then re-approve).
- If the user's institution forbids AI assistance, this does not make the work compliant. State this once, briefly, if relevant.

## Procedure
1. `ms_state.py status <id>`; `ms_state.py backup <report>`.
2. Run `style_scan.py --project <id>` (report-only). Summarise the numbers and findings in chat.
3. Read `academic-writing.md` and the tells below. Work section by section (or the section the user named); change only what the scan or the tells justify.
4. Edit `<id>-report.md`, then `ms_state.py sync`, `style_scan.py` again, `validate_markdown.py`.
5. Report: before/after metrics, what kinds of edits were made, anything you could not fix without user input, and the list of places where user-supplied specifics would help most. Show a few representative before/after sentences.

## What detectors and reviewers react to
Math (for explanation only): perplexity PPL = exp(-mean log p(token | context)); low means every word was the likely one. Burstiness is the spread of that across sentences. Binoculars divides log-perplexity by cross-perplexity between two models; DetectGPT checks whether small rewrites lower the text's probability sharply; watermarks test for a statistical excess of "green" tokens (z = (G - gamma*T) / sqrt(T*gamma*(1-gamma))). Trained classifiers learn the style tells below. All reward text that is predictable, even-paced and generic.

### Tells to remove
- **Vocabulary:** delve, tapestry, pivotal, underscore, testament, showcase, landscape, realm, multifaceted, crucial, vital, seamless, robust, leverage, foster, navigate, holistic, myriad, plethora, comprehensive; "serves as / stands as / boasts" for "is / has".
- **Structure:** "not only X but also Y", "it's not X, it's Y", automatic triplets, a summarising last sentence on every paragraph, intro-body-conclusion symmetry in every section, "Despite these challenges...", every paragraph about the same length.
- **Tone:** inflated significance ("marking a pivotal moment"), trailing "-ing" clauses ("..., highlighting its importance"), promotional wording, vague attribution ("experts argue"), stacked hedges ("it is important to note").
- **Formatting:** heavy em dashes, boldface inside prose, emoji, bullets where prose belongs.
- **Citations:** unverifiable or malformed references. Never "fix" a citation by inventing details.

### Moves that help (in order of value)
1. **Specifics over abstractions:** swap "significant improvement" for the actual number and its source; name the dataset, method, place, date. Only use what the evidence inventory or the user supplies.
2. **Take a position where the evidence supports it:** say which source is stronger, what the limitation really costs, what the author chose and why. Mark interpretation as interpretation.
3. **Vary rhythm:** target sentence-length CV of roughly 0.5-0.8; allow a 5-word sentence next to a 35-word one; vary paragraph length; start sentences in different ways.
4. **Plain verbs and the author's own terms:** "is", "has", "shows", "found"; reuse the user's phrasing from their notes where it is accurate.
5. **Cut, don't pad:** delete throat-clearing openers and recap closers; end a paragraph on its last real point.
6. **Respect register:** formal does not mean generic. Keep it precise and impersonal where the genre requires, but concrete.

## Non-native or low-variety writers
Plain, repetitive wording lowers perplexity and is a known cause of false flags. Widen vocabulary and structure only with words the author would actually use, and keep a revision history (drafts, notes, `.ms/history/`) as the real defence.

## Sources
Wikipedia "Signs of AI writing"; Mitchell et al. 2023 (DetectGPT); Hans et al. 2024 (Binoculars); Kirchenbauer et al. 2023 (watermark); Liang et al. 2023 (bias against non-native writers); Krishna et al. 2023 (DIPPER); Sadasivan et al. 2023 (reliability limits).
