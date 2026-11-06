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
Add a type by adding a file; `ms_state.py init --doctype <name>`. Shipped: research-report, technical-report, thesis, ieee-report. Types such as literature review, project report, experiment report, system design document and research proposal are not yet defined (add as needed; see README).
Assignment guidelines override doctype defaults: record the differences in `plan.md` and in `project-config.yaml`.

## Per-project overrides
`project-config.yaml` may set `required_sections`, `recommended_sections` and `require_abstract`; they replace the document-type values for that project (use this when assignment guidelines name different sections). Record the source in `plan.md`.
