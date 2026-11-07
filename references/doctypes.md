# Document types

Each type is one file `doctypes/<name>.yaml` (restricted YAML: maps, lists, scalars):
```yaml
name: research-report
description: …
require_abstract: true
top_level_division: section        # section | chapter
latex_defaults: templates/latex/article.yaml
citation_style: numeric            # numeric | author-year
required_sections: [Introduction, "Methodology|Methods", …]   # | separates accepted alternatives
recommended_sections: […]
```
Add a type by adding a file; `ms_state.py init --doctype <name>`. `ms_state.py doctypes` lists all. Shipped: research-report, technical-report, thesis, thesis-formal, ieee-report, literature-review, project-report, experiment-report, research-proposal, dissertation-proposal, system-design-document, case-study, white-paper, policy-brief, conference-paper, acm-paper, llncs-paper, elsevier-paper, revtex-paper, preprint.

Optional doctype keys: `layout:` (one-level map of whitelisted layout defaults, see `latex-production.md`); `citation_style:` (any value from `ms_state.py layouts`); `pandoc_template:`, `lua_filters:` (paths relative to the skill); `cite_command:` and `fig_abbrev:` (BibTeX venue styles); `layout_options:` (list of layout keys a custom template honours, or `all`); `frontmatter: true` (accepts the `frontmatter:` config block, thesis-formal only).

Venue types expect author front matter as a list of `{name, affiliation, email}` maps; the key list is in a comment at the top of `templates/latex/<venue>.latex`. Generic article-based types flatten map authors to `Name (Affiliation)`.
Assignment guidelines override doctype defaults: record the differences in `plan.md` and in `project-config.yaml`.

## Per-project overrides
`project-config.yaml` may set `required_sections`, `recommended_sections` and `require_abstract`; they replace the document-type values for that project (use this when assignment guidelines name different sections). Record the source in `plan.md`.
