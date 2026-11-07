#!/usr/bin/env python3
"""Deterministic validation of a ManuScript Markdown draft.

Usage:
  validate_markdown.py --project ID [--root DIR]     validate project draft, write reports, record in state
  validate_markdown.py --file draft.md [--bib refs.bib] [--plan plan.md] [--doctype file.yaml] [--max-words N]

Exit codes: 0 = no errors, 1 = errors found, 2 = usage/IO problem.
Report categories: errors (block approval), warnings, suggestions, confirmations (need user decision).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402
import ms_state as S  # noqa: E402
from validate_references import parse_bib  # noqa: E402
import layout as L  # noqa: E402

RAW_TEX_RE = re.compile(r"(?<![\\\w])\\(?:input|include|includeonly|openin|openout|write|read|immediate|usepackage|RequirePackage|documentclass|"
                        r"def|edef|gdef|xdef|let|newcommand|renewcommand|providecommand|newwrite|newread|catcode|csname|special|directlua|"
                        r"verbatiminput|lstinputlisting|includegraphics|subfile|import|begin|end)\b|\\write18")
NARRATIVE_CITE_RE = re.compile(r"(?<![\w@.])@([A-Za-z0-9_][\w:.\-]*\w)(?!\w)")
PLACEHOLDER_RE = re.compile(r"\[\[[^\]]*\]\]|\b(?:TODO|TBD|FIXME|XXX)\b|<!--\s*(?:EVIDENCE-NEEDED|TODO)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:\{(?:#([^}\s]+))?[^}]*\})?\s*#*\s*$")
IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)(?:\{([^}]*)\})?")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(#([^)\s]+)\)")
CITE_GROUP_RE = re.compile(r"\[([^\]\n]*@[^\]\n]*)\]")
CITE_KEY_RE = re.compile(r"(?:^|[;\s\-])@([A-Za-z0-9_][A-Za-z0-9_:.#$%&+?<>~/\-]*[A-Za-z0-9_])")
TABLE_CAP_RE = re.compile(r"^(?:Table)?:\s+(.*?)(?:\s*\{#([^}\s]+)[^}]*\})?\s*$")
PIPE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def auto_id(text):
    t = re.sub(r"[^\w\s\-.]", "", text.lower())
    t = re.sub(r"^[^a-z]+", "", t)
    return re.sub(r"\s+", "-", t.strip()) or "section"


def norm_title(t):
    t = re.sub(r"^\s*(?:[\dIVXivx]+(?:\.[\dA-Za-z]+)*\.?|Chapter\s+\d+:?|Appendix\s+[A-Z]:?)\s+", "", t.strip())
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def split_front_matter(text):
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[4:end], text[end + 4:].lstrip("\n"), text[:end + 4].count("\n") + 1
    return None, text, 0


def fm_keys(fm):
    return set(re.findall(r"^([A-Za-z_][\w-]*):", fm or "", flags=re.M))


def plan_structure(plan_text):
    """Titles from the '## Approved structure' bullet list in plan.md, as (level, normalized title)."""
    m = re.search(r"^##\s+Approved structure\s*$(.*?)(?=^##\s|\Z)", plan_text, flags=re.M | re.S)
    if not m:
        return None
    items = []
    for line in m.group(1).splitlines():
        b = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if b:
            title = re.sub(r"\s+[\u2014\-:].*$", "", b.group(2)) if re.search(r"\s[\u2014]\s", b.group(2)) else b.group(2)
            items.append((len(b.group(1)) // 2 + 1, norm_title(title)))
    return items or None


def validate(path, bib_path=None, plan_path=None, doctype=None, config=None, base_dir=None):
    res = {"errors": [], "warnings": [], "suggestions": [], "confirmations": [], "stats": {}}

    def add(kind, line, code, msg):
        res[kind].append({"line": line, "code": code, "message": msg})

    raw = C.read_text(path)
    base_dir = base_dir or os.path.dirname(os.path.abspath(path))
    fm, body, fm_lines = split_front_matter(raw)
    keys = fm_keys(fm)
    if "title" not in keys:
        add("errors", 1, "no-title", "Front matter has no 'title:' field.")
    if config and config.get("require_abstract") is not None:
        doctype = dict(doctype or {}, require_abstract=config["require_abstract"])
    if doctype and doctype.get("require_abstract") and "abstract" not in keys:
        add("errors", 1, "no-abstract", "Document type requires an 'abstract:' field in front matter.")
    if config and (config.get("layout") is not None or config.get("citation_style") is not None or config.get("frontmatter") is not None):
        for msg in L.check_config(doctype or {}, config):  # CSL styles (apa7, vancouver, ...) are valid; typos are not
            add("errors", 1, "invalid-config", msg)
    if doctype and doctype.get("frontmatter"):  # opt-in formal thesis front matter: missing pieces are warnings, never errors
        cfgfm = (config or {}).get("frontmatter")
        cfgfm = cfgfm if isinstance(cfgfm, dict) else {}
        for field, label in (("author", "author"), ("date", "date"), ("institution", "institution"), ("department", "department"),
                             ("degree", "degree"), ("supervisor", "supervisor")):
            if field not in keys and cfgfm.get(field) in (None, "", []):
                add("warnings", 1, "frontmatter-missing", "Formal front matter: no %s (set '%s:' in the report front matter or "
                    "'frontmatter: %s' in project-config.yaml); the cover page will omit it." % (label, field, field))
        if "declaration" not in keys and not cfgfm.get("declaration"):
            add("warnings", 1, "frontmatter-missing", "Formal front matter: no declaration/originality statement (set 'declaration:' or 'frontmatter: declaration: true').")
        if "abstract" in keys and "keywords" not in keys:
            add("warnings", 1, "frontmatter-missing", "Formal front matter: abstract has no 'keywords:' list.")
    clean = C.strip_code(body)
    lines = clean.splitlines()

    # headings
    heads = []  # (line, level, title, id)
    for i, ln in enumerate(lines, 1):
        m = HEADING_RE.match(ln)
        if m:
            heads.append((i + fm_lines, len(m.group(1)), m.group(2).strip(), m.group(3) or auto_id(m.group(2))))
    if not heads:
        add("errors", 1, "no-headings", "Document contains no headings.")
    prev = 0
    for ln, lvl, title, _ in heads:
        if lvl > prev + 1 and not (prev == 0 and lvl <= 2):
            add("errors", ln, "heading-skip", "Heading level jumps from %d to %d at %r." % (prev, lvl, title))
        if not title:
            add("errors", ln, "heading-empty", "Empty heading.")
        prev = lvl
    seen = {}
    for ln, lvl, title, hid in heads:
        if hid in seen:
            add("warnings", ln, "duplicate-heading-id", "Heading id %r duplicates line %d; internal links ambiguous." % (hid, seen[hid]))
        seen.setdefault(hid, ln)
    # empty sections: no non-blank content and no subsection
    for idx, (ln, lvl, title, _) in enumerate(heads):
        start = ln - fm_lines
        end = (heads[idx + 1][0] - fm_lines - 1) if idx + 1 < len(heads) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        content = re.sub(r"<!--.*?-->", "", content, flags=re.S).strip()
        nxt_deeper = idx + 1 < len(heads) and heads[idx + 1][1] > lvl
        if not content and not nxt_deeper and not re.fullmatch(r"(?i)references|bibliography|works cited", title):
            add("errors", ln, "empty-section", "Section %r is empty." % title)

    # required sections: project config (assignment-specific) overrides the document-type defaults
    doctype = dict(doctype or {})
    for key in ("required_sections", "recommended_sections", "require_abstract"):
        if config and config.get(key) is not None:
            doctype[key] = config[key]
    titles_norm = [norm_title(t) for _, _, t, _ in heads]
    for req in (doctype or {}).get("required_sections", []) or []:
        alts = [norm_title(a) for a in str(req).split("|")]
        if not any(t in alts for t in titles_norm):
            add("errors", 1, "missing-required-section", "Required section missing: %s" % req)
    for rec in (doctype or {}).get("recommended_sections", []) or []:
        alts = [norm_title(a) for a in str(rec).split("|")]
        if not any(t in alts for t in titles_norm):
            add("suggestions", 1, "missing-recommended-section", "Consider adding section: %s" % rec)

    # plan consistency
    if plan_path and os.path.isfile(plan_path):
        ps = plan_structure(C.read_text(plan_path))
        if ps is None:
            add("warnings", 1, "plan-no-structure", "plan.md has no '## Approved structure' list; cannot check structure.")
        else:
            plan_titles = [t for _, t in ps]
            miss = [t for t in plan_titles if t not in titles_norm]
            extra = [t for t in titles_norm if t not in plan_titles]
            for t in miss:
                add("warnings", 1, "plan-section-missing", "Section in approved plan not found in draft: %r" % t)
            for t in extra:
                add("warnings", 1, "section-not-in-plan", "Draft section not in approved plan: %r" % t)
            common_plan = [t for t in plan_titles if t in titles_norm]
            common_draft = [t for t in titles_norm if t in plan_titles]
            if common_plan != common_draft:
                add("confirmations", 1, "section-order-differs", "Section order differs from the approved plan; confirm this is intended.")

    # figures
    fig_ids, tbl_ids = {}, {}
    for i, ln in enumerate(lines, 1):
        for m in IMG_RE.finditer(ln):
            alt, src, attrs = m.group(1), m.group(2), m.group(3) or ""
            idm = re.search(r"#([^\s}]+)", attrs)
            lineno = i + fm_lines
            if not alt.strip():
                add("errors", lineno, "figure-no-caption", "Image %r has no caption (alt text)." % src)
            if not idm:
                add("warnings", lineno, "figure-no-label", "Image %r has no {#fig-...} label; it cannot be cross-referenced." % src)
            else:
                fid = idm.group(1)
                if fid in fig_ids:
                    add("errors", lineno, "duplicate-label", "Duplicate figure label %r." % fid)
                fig_ids[fid] = lineno
            if not re.match(r"^[a-z]+://", src) and not os.path.isfile(os.path.join(base_dir, src)):
                add("errors", lineno, "figure-missing-file", "Image file not found: %s" % src)
    # figures built from specs: warn when the figure is out of date with its spec/data
    mpath = os.path.join(base_dir, ".ms", "figures", "manifest.json")
    if os.path.isfile(mpath):
        try:
            for name, ent in C.read_json(mpath).items():
                sp = os.path.join(base_dir, ent["spec"])
                stale = not os.path.isfile(sp) or C.sha256_file(sp) != ent["spec_sha"] or any(
                    not os.path.isfile(os.path.join(base_dir, i["path"])) or C.sha256_file(os.path.join(base_dir, i["path"])) != i["sha"]
                    for i in ent.get("inputs", []))
                if stale:
                    add("warnings", 1, "figure-out-of-date", "Figure %r is out of date with its spec/data; run build_figures.py." % name)
        except (ValueError, KeyError, OSError):
            add("warnings", 1, "figure-manifest-unreadable", "manifest.json could not be read.")
    # tables
    n_pipe = 0

    def cap_at(idx):
        if 0 <= idx < len(lines) and lines[idx].strip().startswith((":", "Table:")):
            return TABLE_CAP_RE.match(lines[idx].strip())
        return None

    i = 0
    while i < len(lines):
        if i > 0 and "|" in lines[i] and PIPE_SEP_RE.match(lines[i]) and "|" in lines[i - 1]:
            s0 = i - 1
            while s0 > 0 and "|" in lines[s0 - 1]:
                s0 -= 1
            e0 = i
            while e0 + 1 < len(lines) and "|" in lines[e0 + 1]:
                e0 += 1
            n_pipe += 1
            cap = None
            for cand in (e0 + 1, e0 + 2, s0 - 1, s0 - 2):
                if cand in (e0 + 2, s0 - 2) and not (0 <= (cand - 1 if cand > e0 else cand + 1) < len(lines)
                                                     and lines[cand - 1 if cand > e0 else cand + 1].strip() == ""):
                    continue
                cap = cap_at(cand)
                if cap:
                    break
            lineno = s0 + 1 + fm_lines
            if cap is None:
                add("errors", lineno, "table-no-caption", "Table has no caption line ('Table: caption {#tbl-id}').")
            elif not cap.group(2):
                add("warnings", lineno, "table-no-label", "Table caption has no {#tbl-...} label.")
            else:
                if cap.group(2) in tbl_ids:
                    add("errors", lineno, "duplicate-label", "Duplicate table label %r." % cap.group(2))
                tbl_ids[cap.group(2)] = lineno
            i = e0
        i += 1

    # internal links
    all_ids = set(h[3] for h in heads) | set(fig_ids) | set(tbl_ids)
    for m in re.finditer(r"\{#([^}\s]+)", clean):
        all_ids.add(m.group(1))
    referenced = set()
    for i, ln in enumerate(lines, 1):
        for m in LINK_RE.finditer(ln):
            tgt = m.group(1)
            referenced.add(tgt)
            if tgt not in all_ids:
                add("errors", i + fm_lines, "broken-link", "Internal link target #%s does not exist." % tgt)
    for fid, ln in fig_ids.items():
        if fid not in referenced:
            add("warnings", ln, "figure-unreferenced", "Figure %r is never referenced in the text." % fid)
    for tid, ln in tbl_ids.items():
        if tid not in referenced:
            add("warnings", ln, "table-unreferenced", "Table %r is never referenced in the text." % tid)

    # citations
    cited = {}
    for i, ln in enumerate(lines, 1):
        for g in CITE_GROUP_RE.finditer(ln):
            for k in CITE_KEY_RE.finditer(g.group(1)):
                cited.setdefault(k.group(1), i + fm_lines)
    bib = None
    if bib_path and os.path.isfile(bib_path):
        bib = parse_bib(C.read_text(bib_path))[0]
    if bib is not None:  # narrative citations (@key outside brackets) count only when the key exists
        for i, ln in enumerate(lines, 1):
            for m in re.finditer(r"(?<![\w@.])@([A-Za-z0-9_][\w:.\-]*\w)", ln):
                if m.group(1) in bib:
                    cited.setdefault(m.group(1), i + fm_lines)
    for key, ln in sorted(cited.items(), key=lambda kv: kv[1]):
        if bib is None:
            add("errors", ln, "no-bibliography", "Citation @%s used but no bibliography file exists." % key)
        elif key not in bib:
            add("errors", ln, "missing-bib-entry", "Citation @%s has no entry in the bibliography." % key)
    if bib is not None:
        for key in bib:
            if key not in cited:
                add("warnings", 1, "unused-bib-entry", "Bibliography entry %r is never cited." % key)
    if cited and not any(re.fullmatch(r"(?i)references|bibliography|works cited", t) for t in titles_norm):
        add("suggestions", 1, "no-reference-section", "Citations present but no 'References' heading. Pandoc appends the bibliography at the end unless a heading is provided.")

    # raw LaTeX is NOT passed through to the .tex/.docx (it is rendered inert as text): tell the author
    nomath = re.sub(r"\$\$.*?\$\$", lambda m: "\n" * m.group(0).count("\n"), clean, flags=re.S)
    nomath = re.sub(r"(?<![\\\w$])\$[^\s$](?:[^$\n]*[^\s$\\])?\$(?![\w$])", " ", nomath)
    for i, ln in enumerate(nomath.splitlines(), 1):
        m = RAW_TEX_RE.search(ln)
        if m:
            add("warnings", i + fm_lines, "raw-latex-ignored",
                "Raw LaTeX %s is not passed through to LaTeX or Word (it is shown as plain text). Use Markdown, $...$ / $$...$$ for math, "
                "and the layout/frontmatter options in project-config.yaml instead." % m.group(0))
            break
    # MLA 9: a narrative cite without a locator can render with empty parentheses in some builds; ask for an explicit locator
    try:
        style = L.resolve_citation_style(doctype or {}, config or {})
    except ValueError:
        style = None
    if style == "mla9" and bib is not None:
        for i, ln in enumerate(lines, 1):
            ln2 = re.sub(r"(?<![\w@])@[\w:.\-]+\s*\[[^\]]*\]", " ", ln)  # '@key [p. 5]' is fine
            ln2 = CITE_GROUP_RE.sub(" ", ln2)                                # so are bracketed cites
            for m in NARRATIVE_CITE_RE.finditer(ln2):
                if m.group(1) in bib:
                    add("warnings", i + fm_lines, "mla-narrative-no-locator",
                        "MLA 9: narrative citation @%s has no locator; write '@%s [p. 5]' or '[@%s, p. 5]' (or ignore if the work has no pages)."
                        % (m.group(1), m.group(1), m.group(1)))
                    break

    # placeholders (on raw body, code excluded)
    for i, ln in enumerate(lines, 1):
        for m in PLACEHOLDER_RE.finditer(ln):
            add("errors", i + fm_lines, "unresolved-placeholder", "Unresolved placeholder: %s" % m.group(0)[:60])

    # length
    text_only = re.sub(r"<!--.*?-->", "", clean, flags=re.S)
    text_only = re.sub(r"!\[[^\]]*\]\([^)]*\)|\([^)]*\)|[#*_`>|\[\]{}]|-{3,}", " ", text_only)
    words = len(re.findall(r"[A-Za-z0-9][\w'’\-]*", text_only))
    res["stats"] = {"words": words, "headings": len(heads), "figures": len(fig_ids), "tables": n_pipe,
                    "citations": len(cited), "bib_entries": len(bib) if bib is not None else None}
    limits = (config or {}).get("limits") or {}
    mx, mn = limits.get("max_words"), limits.get("min_words")
    if mx and words > mx:
        add("errors", 1, "over-word-limit", "Word count %d exceeds limit %d." % (words, mx))
    elif mx and words > 0.95 * mx:
        add("warnings", 1, "near-word-limit", "Word count %d is within 5%% of limit %d." % (words, mx))
    if mn and words < mn:
        add("errors", 1, "under-word-minimum", "Word count %d is below minimum %d." % (words, mn))
    if limits.get("max_pages"):
        add("confirmations", 1, "page-limit-unmeasured", "Page limit %s cannot be measured from Markdown; verify after PDF build." % limits["max_pages"])
    return res


def to_markdown_report(res, source):
    out = ["# Markdown validation report", "", "Source: `%s`" % source, "",
           "Words: %(words)s · Headings: %(headings)s · Figures: %(figures)s · Tables: %(tables)s · Citations: %(citations)s" % res["stats"], ""]
    for kind, title in (("errors", "Errors (block approval)"), ("warnings", "Warnings"),
                        ("suggestions", "Suggestions"), ("confirmations", "Items requiring user confirmation")):
        out.append("## %s (%d)" % (title, len(res[kind])))
        out.extend("- line %s [%s] %s" % (i["line"], i["code"], i["message"]) for i in res[kind]) if res[kind] else out.append("- none")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project"); ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--file"); ap.add_argument("--bib"); ap.add_argument("--plan"); ap.add_argument("--doctype")
    ap.add_argument("--max-words", type=int); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    config = {}
    doctype = None
    try:
        if a.file:
            path, bib, plan = a.file, a.bib, a.plan
            if a.doctype:
                doctype = C.load_yaml(a.doctype)
            if a.max_words:
                config = {"limits": {"max_words": a.max_words}}
            outdir, st, pid = None, None, None
        else:
            pid = S.resolve(root, a.project)
            st = S.load(root, pid)
            d = S.pdir(root, pid)
            path, bib, plan = S.artifact_path(root, pid, "draft"), S.artifact_path(root, pid, "bibliography"), S.artifact_path(root, pid, "plan")
            cfg = S.artifact_path(root, pid, "config")
            config = C.load_yaml(cfg) if os.path.isfile(cfg) else {}
            dt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "doctypes", "%s.yaml" % st["doctype"])
            doctype = C.load_yaml(dt) if os.path.isfile(dt) else None
            outdir = os.path.join(d, ".ms", "validation")
        if not os.path.isfile(path):
            print("ERROR: draft not found: %s" % path, file=sys.stderr)
            return 2
        res = validate(path, bib, plan, doctype, config)
    except (S.StateError, ValueError, OSError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    h = C.sha256_file(path)
    res["source"] = os.path.basename(path); res["sha256"] = h; res["validated_at"] = C.now()
    if outdir:
        C.write_json(os.path.join(outdir, "markdown-validation.json"), res)
        with open(os.path.join(outdir, "markdown-validation.md"), "w", encoding="utf-8") as f:
            f.write(to_markdown_report(res, os.path.basename(path)))
        st["last_validation"] = {"at": res["validated_at"], "sha256": h, "errors": len(res["errors"]),
                                 "warnings": len(res["warnings"]), "report": ".ms/validation/markdown-validation.md"}
        S.save(root, pid, st)
    print(json.dumps(res, indent=2) if a.json else to_markdown_report(res, os.path.basename(path)))
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
