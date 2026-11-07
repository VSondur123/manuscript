#!/usr/bin/env python3
"""Layout options + citation styles: the single merge point between doctype, project config and pandoc.

Precedence (lowest to highest):  built-in defaults < doctype (`layout:` / `citation_style:`)
                                  < project-config.yaml (`layout:` / `citation_style:`).
Assignment guidelines outrank everything: the model copies their requirements INTO project-config.yaml
(that file is where assignment-specific overrides live), so config always wins over a doctype.

Public API (stdlib only; depends only on ms_common; raises ValueError with a message that lists allowed values):
  resolve_layout(dt, cfg)            -> {key: normalised value} of the layout keys that are set
  resolve_citation_style(dt, cfg)    -> style name or None
  check_config(dt, cfg, ...)         -> [error strings]  (all problems at once, never raises)
  build_plan(dt, cfg, skill_dir, latex_dir, custom_template=None, preview_marker=None) -> Plan
  describe()                         -> text listing every allowed option (for `ms_state.py layouts`)

How to extend (new doctype / venue template):
  * doctype YAML may carry   citation_style: apa7        and a one-level map   layout: {paper: letter, columns: 2}
  * a doctype with its own pandoc_template honours NO layout option unless it lists them:
        layout_options: [paper, font_size, margins]
    (layout_options: all  = every key).  CSL styles also need `$if(csl-refs)$` support in that template.
  * new CSL style: drop the .csl into templates/csl/ (record it in templates/csl/NOTICE.md) and add one entry to
    CITATION_STYLES below.  Values are whitelisted, never free text: they reach LaTeX and pandoc.

Nothing here writes outside `latex_dir` and nothing is returned unless a layout/CSL style is actually set, so the
default (no layout, BibTeX/natbib) command line and .tex output are unchanged.
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402

# ---------------------------------------------------------------- citation styles
# name -> (engine, csl file under templates/csl or None, natbib/BibTeX settings or None, description)
CITATION_STYLES = {
    "numeric":   {"engine": "bibtex", "description": "numbered [1], natbib + plainnat (default)"},
    "author-year": {"engine": "bibtex", "description": "(Author, Year), natbib authoryear"},
    "ieee":      {"engine": "bibtex", "description": "numbered, BibTeX IEEEtran.bst",
                  "natbib": {"biblio-style": "IEEEtran", "natbiboptions": "numbers,sort&compress"}},
    "apa7":      {"engine": "csl", "csl": "apa.csl", "description": "APA 7th edition (Author, Year)"},
    "harvard":   {"engine": "csl", "csl": "harvard-cite-them-right.csl", "description": "Harvard, Cite Them Right 12th ed. (Author, Year)"},
    "mla9":      {"engine": "csl", "csl": "modern-language-association.csl", "description": "MLA 9th edition (Author)"},
    "chicago-author-date": {"engine": "csl", "csl": "chicago-author-date.csl", "description": "Chicago 18th ed. author-date"},
    "chicago-notes": {"engine": "csl", "csl": "chicago-notes-bibliography.csl", "description": "Chicago 18th ed. notes and bibliography (footnotes)"},
    "vancouver": {"engine": "csl", "csl": "nlm-citation-sequence-brackets.csl", "description": "Vancouver / NLM numbered [1]"},
}

# ---------------------------------------------------------------- layout options
PAPERS = ("a4", "letter")
MARGIN_RE = re.compile(r"^(?:0\.[5-9][0-9]?|[1-5](?:\.[0-9]{1,2})?)(?:cm|in)$|^[1-9][0-9](?:\.[0-9])?mm$")
LAYOUT_KEYS = {
    "paper": ("a4", "letter"),
    "font_size": ("10", "11", "12"),
    "spacing": ("single", "onehalf", "double"),
    "margins": None,  # regex, see MARGIN_RE: <number>cm|mm|in, e.g. 2.5cm, 25mm, 1in
    "columns": ("1", "2"),
    "font": ("cm", "times", "palatino", "libertinus", "helvetica-sans"),
    "header": ("none", "running-title", "title-author"),
    "page_numbers": ("bottom-center", "bottom-right", "top-right", "none"),
    "heading_numbering": ("on", "off"),
    "caption_position": ("bottom", "top"),
    "table_style": ("booktabs", "plain"),
    "colour": ("screen", "print"),
}
LAYOUT_NOTES = {
    "paper": "paper size", "font_size": "base font size in pt (document class option)",
    "spacing": "line spacing: single=1.0, onehalf=1.5, double=2.0",
    "margins": "all four margins, <number>cm|mm|in (e.g. 2.5cm, 25mm, 1in; 0.5-5.99 cm/in, 10-99 mm)",
    "columns": "2 = two-column; article-based doctypes only (tables are set as single-column tabulars)",
    "font": "text font family (TeX Gyre/Libertinus/Nimbus faces shipped in the Tectonic bundle)",
    "header": "running header text; the title/author come from the document metadata",
    "page_numbers": "page number placement (also applied to chapter-opening pages)",
    "heading_numbering": "numbered section headings",
    "caption_position": "figure captions below (default) or above the figure; table captions are always above",
    "table_style": "booktabs (default) or plain horizontal rules",
    "colour": "screen = coloured links; print = black links (no colour)",
}
SPACING = {"single": "1.0", "onehalf": "1.5", "double": "2.0"}

# font name -> LaTeX preamble (XeTeX/Tectonic branch uses font FILES shipped in the bundle; pdfTeX uses packages)
_TG = "[Extension=.otf,UprightFont=*-regular,BoldFont=*-bold,ItalicFont=*-italic,BoldItalicFont=*-bolditalic]"
FONT_PREAMBLE = {
    "cm": "",
    "times": ("\\ifPDFTeX\n  \\usepackage{mathptmx}\n\\else\n  \\setmainfont{texgyretermes}%s\n\\fi" % _TG),
    "palatino": ("\\ifPDFTeX\n  \\usepackage{mathpazo}\n\\else\n  \\setmainfont{texgyrepagella}%s\n\\fi" % _TG),
    "libertinus": "\\usepackage{libertinus}",
    "helvetica-sans": ("\\ifPDFTeX\n  \\usepackage[scaled=0.95]{helvet}\n\\else\n  \\setsansfont{texgyreheros}%s\n\\fi\n"
                       "\\renewcommand{\\familydefault}{\\sfdefault}" % _TG),
}


# ---------------------------------------------------------------- formal thesis front/back matter (opt-in doctype)
# config key -> kind. `frontmatter:` in project-config.yaml is only accepted when the doctype declares `frontmatter: true`
# (thesis-formal). Values become pandoc METADATA (--metadata-file), never LaTeX text: pandoc escapes them, and strings are
# additionally backslash-escaped here so a config value is always literal (no raw TeX or Markdown markup).
FRONTMATTER_KEYS = {
    "institution": "text", "faculty": "text", "department": "text", "degree": "text", "date": "text",
    "supervisor": "text-or-list",          # one name or a list of names
    "logo": "path",                        # image path; copied and sha256-locked by `ms_state.py lock-logo`
    "declaration": "bool-or-text",         # true = standard originality statement, text = your own wording
    "copyright": "bool-or-text",           # true = "Copyright (c) <year> <author>. All rights reserved."
    "dedication": "text", "acknowledgements": "text",
    "toc": "bool", "lof": "bool", "lot": "bool",
    "roman_front_matter": "bool",          # roman page numbers for the front matter, arabic from chapter 1
}
FRONTMATTER_NOTES = {
    "institution": "university name", "faculty": "faculty / school", "department": "department", "degree": "e.g. Master of Science in Data Science",
    "date": "cover date (default: the date in the report front matter)", "supervisor": "name or list of names",
    "logo": "png/jpg/pdf path; run ms_state.py lock-logo to copy + hash it", "declaration": "true or your own statement",
    "copyright": "true or your own notice", "dedication": "short text", "acknowledgements": "short text (longer: use report front matter)",
    "toc": "table of contents (default true)", "lof": "list of figures", "lot": "list of tables",
    "roman_front_matter": "roman numerals for front matter",
}
LOGO_EXT = ("png", "jpg", "jpeg", "pdf")
_PUNCT = re.compile(r"([!-/:-@\[-`{-~])")


def literal(v):
    """Make a config string literal for pandoc's Markdown reader: backslash-escape every ASCII punctuation character."""
    return _PUNCT.sub(r"\\\1", " ".join(str(v).split()))


def resolve_frontmatter(dt, cfg, errors=None):
    """Validated `frontmatter:` map from the project config ({} when absent). Raises ValueError, or appends all problems to `errors`."""
    block = (cfg or {}).get("frontmatter")
    out = {}

    def bad(msg):
        if errors is None:
            raise ValueError(msg)
        errors.append(msg)

    if block is None:
        return out
    if not (dt or {}).get("frontmatter"):
        bad("project-config.yaml: 'frontmatter' is only supported by document types with formal front matter (doctype thesis-formal); "
            "this document type would ignore it")
        return out
    if not isinstance(block, dict):
        bad("project-config.yaml: 'frontmatter' must be a map of option: value")
        return out
    for k, v in block.items():
        kind = FRONTMATTER_KEYS.get(k)
        if kind is None:
            bad("frontmatter: unknown option %r; allowed options: %s" % (k, ", ".join(FRONTMATTER_KEYS)))
        elif v is None:
            continue
        elif kind == "bool":
            if not isinstance(v, bool):
                bad("frontmatter.%s: expected true or false, got %r" % (k, v))
            else:
                out[k] = v
        elif kind == "bool-or-text":
            if isinstance(v, bool) or isinstance(v, str):
                out[k] = v
            else:
                bad("frontmatter.%s: expected true or text, got %r" % (k, v))
        elif kind == "text-or-list" and isinstance(v, list):
            if not v or not all(isinstance(x, (str, int, float)) and not isinstance(x, bool) for x in v):
                bad("frontmatter.%s: expected a list of names" % k)
            else:
                out[k] = [str(x) for x in v]
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            v = str(v)
            if kind == "path" and (not re.fullmatch(r"[\w./ ~+-]+\.(%s)" % "|".join(LOGO_EXT), v, flags=re.I) or ".." in v.split("/") or v.startswith(("/", "~"))):
                bad("frontmatter.logo: %r must be a plain file path (relative, inside the project) ending in %s" % (v, ", ".join("." + e for e in LOGO_EXT)))
            else:
                out[k] = v
        else:
            bad("frontmatter.%s: expected a single text value, got %r" % (k, v))
    return out


def frontmatter_metadata(fm, logo_name=None):
    """pandoc metadata dict for the resolved frontmatter config (values literal-escaped; booleans stay booleans)."""
    md = {}
    for k, v in fm.items():
        if k == "logo":
            continue
        if k in ("declaration", "copyright"):
            if v is True:
                md["include-" + k] = True
            elif isinstance(v, str):
                md[k] = literal(v)
        elif k == "roman_front_matter":
            if v:
                md["roman-front"] = True
        elif isinstance(v, bool):
            md[k] = v
        elif isinstance(v, list):
            md[k] = [literal(x) for x in v]
        else:
            md[k] = literal(v)
    if logo_name:
        md["logo"] = literal(logo_name)
    return md


def skill_csl_dir(skill_dir):
    return os.path.join(skill_dir, "templates", "csl")


def _norm(key, v):
    """YAML gives ints/bools for 11, 2, yes/no; turn into the canonical whitelist string (or raise)."""
    if v is None:
        return None
    if isinstance(v, bool):
        v = "on" if v else "off"
    if isinstance(v, float) and v == int(v):
        v = int(v)
    if not isinstance(v, (str, int)):
        raise ValueError("layout.%s: expected a single value, got %r" % (key, v))
    return str(v).strip()


def _validate_one(key, v):
    allowed = LAYOUT_KEYS[key]
    if key == "margins":
        if not MARGIN_RE.match(v):
            raise ValueError("layout.margins: %r is not allowed; use <number>cm|mm|in such as 2.5cm, 25mm or 1in" % v)
    elif v not in allowed:
        raise ValueError("layout.%s: %r is not allowed; allowed values: %s" % (key, v, ", ".join(allowed)))
    return v


def resolve_layout(dt, cfg, errors=None):
    """Merged + validated layout dict (only keys that are set). Raises ValueError listing allowed values, or, when an
    `errors` list is passed, appends every problem to it and keeps going (used by check_config)."""
    out = {}

    def bad(msg):
        if errors is None:
            raise ValueError(msg)
        errors.append(msg)

    for src, label in ((dt, "doctype"), (cfg, "project-config.yaml")):
        block = (src or {}).get("layout")
        if block is None:
            continue
        if not isinstance(block, dict):
            bad("%s: 'layout' must be a map of option: value" % label)
            continue
        for k, v in block.items():
            if k not in LAYOUT_KEYS:
                bad("%s: unknown layout option %r; allowed options: %s" % (label, k, ", ".join(LAYOUT_KEYS)))
                continue
            try:
                nv = _norm(k, v)
                if nv is not None:
                    out[k] = _validate_one(k, nv)
            except ValueError as e:
                bad(str(e))
    return out


def resolve_citation_style(dt, cfg):
    v = (cfg or {}).get("citation_style")
    if v is None:
        v = (dt or {}).get("citation_style")
    if v is None:
        return None
    if not isinstance(v, str) or v not in CITATION_STYLES:
        raise ValueError("citation_style: %r is not allowed; allowed values: %s" % (v, ", ".join(CITATION_STYLES)))
    return v


def _supported_layout_keys(dt, custom_template):
    """Keys the doctype's template honours. Stock article/book pandoc template: all. Custom template: opt in."""
    if not (dt.get("pandoc_template") or custom_template):
        return set(LAYOUT_KEYS)
    declared = dt.get("layout_options")
    if declared == "all":
        return set(LAYOUT_KEYS)
    return set(declared or []) if isinstance(declared, list) else set()


def _template_has_csl(path):
    try:
        text = C.read_text(path)
        return "csl-refs" in text or "$common.latex()$" in text  # pandoc's shared preamble partial carries the CSL support
    except OSError:
        return False


def check_config(dt, cfg, skill_dir=None, root=None, template_override=None):
    """All configuration problems as a list of strings (empty = fine)."""
    dt, cfg = dt or {}, cfg or {}
    errors = []
    style = None
    layout = resolve_layout(dt, cfg, errors)
    try:
        style = resolve_citation_style(dt, cfg)
    except ValueError as e:
        errors.append(str(e))
    resolve_frontmatter(dt, cfg, errors)
    custom = template_override or cfg.get("template")
    if layout:
        ok = _supported_layout_keys(dt, custom)
        bad = sorted(k for k in layout if k not in ok)
        if bad:
            errors.append("layout option(s) %s are not supported with this custom pandoc template (%s); "
                          "remove them or let the template declare them in 'layout_options'"
                          % (", ".join(bad), custom or dt.get("pandoc_template")))
        base = _base_defaults(dt, skill_dir) if skill_dir else {}
        if layout.get("columns") == "2" and base and (base.get("variables") or {}).get("documentclass") != "article":
            errors.append("layout.columns: 2 is only supported for article-based document types (this one uses %s)"
                          % (base.get("variables") or {}).get("documentclass"))
    if style and CITATION_STYLES[style]["engine"] == "csl":
        tpl = custom and (os.path.join(root, custom) if root else custom)
        if dt.get("pandoc_template") and skill_dir:
            tpl = os.path.join(skill_dir, dt["pandoc_template"])
        if tpl and not _template_has_csl(tpl):
            errors.append("citation_style %s needs pandoc --citeproc, but the custom template %s has no $csl-refs$ support; "
                          "use numeric, author-year or ieee (BibTeX) with this template" % (style, tpl))
        if skill_dir and not os.path.isfile(os.path.join(skill_csl_dir(skill_dir), CITATION_STYLES[style]["csl"])):
            errors.append("CSL file missing for %s: templates/csl/%s" % (style, CITATION_STYLES[style]["csl"]))
    return errors


def _base_defaults(dt, skill_dir):
    p = os.path.join(skill_dir, dt.get("latex_defaults", "templates/latex/article.yaml"))
    return C.load_yaml(p) if os.path.isfile(p) else {}


class Plan(object):
    """Result of build_plan. `defaults` is the pandoc --defaults path to use; `args` are extra args to append
    (already in a stable order); `files` {relpath-in-latex_dir: sha256} for everything this plan wrote or points at."""

    def __init__(self):
        self.defaults = None
        self.args = []
        self.pre_args = []        # e.g. -V header-includes for the default-path preview marker
        self.citeproc = False
        self.csl = None           # absolute CSL path
        self.layout = {}
        self.citation_style = None
        self.files = {}           # {path: sha256}
        self.log = []

    def record(self, skill_dir):
        """JSON-able dependency record for state.json (what the approved snapshot's LaTeX depends on)."""
        deps = {}
        for p, h in self.files.items():
            deps[p] = h
        rec = {"citation_style": self.citation_style, "layout": dict(self.layout), "citeproc": self.citeproc,
               "files": deps}
        if self.csl:
            rec["csl"] = {"path": os.path.relpath(self.csl, skill_dir), "sha256": C.sha256_file(self.csl)}
        return rec


def _header_text(layout):
    """LaTeX for header-includes from the whitelisted layout values (no user text is interpolated)."""
    parts = []
    font = layout.get("font")
    if font and FONT_PREAMBLE.get(font):
        parts.append(FONT_PREAMBLE[font])
    if layout.get("caption_position") == "top":
        parts.append("\\usepackage{floatrow}\n\\floatsetup[figure]{capposition=top}\n"
                     "\\setlength{\\LTleft}{\\fill}\\setlength{\\LTright}{\\fill}  % floatrow resets longtable centring")
    if layout.get("table_style") == "plain":
        # booktabs is absent for plain tabulars (columns: 2 / ieee-tables.lua): only restyle when the rules exist
        parts.append("\\makeatletter\n\\AtBeginDocument{\\@ifundefined{toprule}{}{%\n"
                     "\\renewcommand{\\toprule}{\\hline}\\renewcommand{\\midrule}{\\hline}\\renewcommand{\\bottomrule}{\\hline}}}\n\\makeatother")
    if "header" in layout or "page_numbers" in layout:
        header = layout.get("header", "none")
        numbers = layout.get("page_numbers", "bottom-center")
        body = []
        if header == "running-title":
            body.append("\\fancyhead[L]{\\msruntitle}")
        elif header == "title-author":
            body.append("\\fancyhead[L]{\\msrunauthor}\n\\fancyhead[C]{\\msruntitle}")
        if numbers == "bottom-center":
            body.append("\\fancyfoot[C]{\\thepage}")
        elif numbers == "bottom-right":
            body.append("\\fancyfoot[R]{\\thepage}")
        elif numbers == "top-right":
            body.append("\\fancyhead[R]{\\thepage}")
        body.append("\\renewcommand{\\headrulewidth}{%s}\\renewcommand{\\footrulewidth}{0pt}"
                    % ("0.4pt" if header != "none" else "0pt"))
        block = "\\fancyhf{}\n" + "\n".join(body)
        # same settings for the 'plain' style (chapter-opening pages) and the 'fancy' style (all other pages)
        parts.append("\n".join([
            "\\usepackage{fancyhdr}",
            "\\makeatletter",
            "\\AtBeginDocument{\\let\\msruntitle\\@title\\let\\msrunauthor\\@author}",
            "\\makeatother",
            "\\fancypagestyle{plain}{" + block + "}",
            "\\fancypagestyle{fancy}{" + block + "}",
            "\\pagestyle{fancy}"]))
    return "\n".join(parts)


def _merged_defaults(dt, layout, style, skill_dir):
    d = json.loads(json.dumps(_base_defaults(dt, skill_dir)))  # deep copy
    v = d.setdefault("variables", {})
    if style and CITATION_STYLES[style]["engine"] == "csl":
        v.pop("biblio-style", None)
        v.pop("natbiboptions", None)
    elif style and CITATION_STYLES[style].get("natbib"):
        v.update(CITATION_STYLES[style]["natbib"])
    elif style in ("numeric", "author-year"):
        v["natbiboptions"] = "numbers,sort&compress" if style == "numeric" else "authoryear"
        v["biblio-style"] = "plainnat"
    opts = v.get("classoption")
    if isinstance(opts, str):
        opts = [opts]
    opts = list(opts or [])
    if "paper" in layout:
        opts = [o for o in opts if not re.fullmatch(r"(a4|letter)paper", o)] + [layout["paper"] + "paper"]
    if "font_size" in layout:
        opts = [o for o in opts if not re.fullmatch(r"1[012]pt", o)] + [layout["font_size"] + "pt"]
    if layout.get("columns") == "2":
        opts.append("twocolumn")
    elif layout.get("columns") == "1":
        opts = [o for o in opts if o != "twocolumn"]
    if opts:
        v["classoption"] = opts
    if "spacing" in layout:
        v["linestretch"] = float(SPACING[layout["spacing"]])
    if "margins" in layout:
        v["geometry"] = "margin=" + layout["margins"]
    if layout.get("colour") == "print":
        v["colorlinks"] = False
    elif layout.get("colour") == "screen":
        v["colorlinks"] = True
    if layout.get("heading_numbering") == "off":
        d["number-sections"] = False
    elif layout.get("heading_numbering") == "on":
        d["number-sections"] = True
    return d


def build_plan(dt, cfg, skill_dir, latex_dir, custom_template=None, preview_marker=None, root=None, logo=None):
    """Everything the pandoc command needs beyond input/output. Raises ValueError on invalid configuration.

    With no layout, no CSL style and no preview marker the plan is empty: defaults = the doctype's own defaults
    file, args = [] (so the default-path command line is exactly what it was before this module existed)."""
    dt, cfg = dt or {}, cfg or {}
    errs = check_config(dt, cfg, skill_dir=skill_dir, template_override=custom_template, root=root)
    if errs:
        raise ValueError("; ".join(errs))
    plan = Plan()
    plan.layout = resolve_layout(dt, cfg)
    plan.citation_style = resolve_citation_style(dt, cfg)
    plan.defaults = os.path.join(skill_dir, dt.get("latex_defaults", "templates/latex/article.yaml"))
    plan.citeproc = bool(plan.citation_style and CITATION_STYLES[plan.citation_style]["engine"] == "csl")
    # author-year/numeric requested in config but different from what the doctype's defaults file says
    style_changes_natbib = plan.citation_style in ("ieee", "numeric", "author-year") and \
        plan.citation_style != dt.get("citation_style") and not (dt.get("pandoc_template") or custom_template)
    # ieee doctype: template is IEEEtran already; numeric/ieee need no natbib change
    need_merge = bool(plan.layout) or plan.citeproc or style_changes_natbib
    header = _header_text(plan.layout) if plan.layout else ""
    os.makedirs(latex_dir, exist_ok=True)
    for stale in ("pandoc-defaults.yaml", "layout-header.tex", "frontmatter-metadata.json"):  # never leave files from an earlier configuration around
        if os.path.isfile(os.path.join(latex_dir, stale)):
            os.unlink(os.path.join(latex_dir, stale))
    if need_merge:
        merged = _merged_defaults(dt, plan.layout, plan.citation_style, skill_dir)
        dpath = os.path.join(latex_dir, "pandoc-defaults.yaml")
        with open(dpath, "w", encoding="utf-8") as f:
            f.write(json.dumps(merged, indent=2, sort_keys=True) + "\n")  # JSON is valid YAML: quoting can never break
        plan.defaults = dpath
        plan.files["pandoc-defaults.yaml"] = C.sha256_file(dpath)
        plan.log.append("layout/citation merge written to pandoc-defaults.yaml")
    lua = []
    if plan.layout.get("columns") == "2":
        lua.append(os.path.join(skill_dir, "templates", "latex", "ieee-tables.lua"))
    if preview_marker is not None:
        if header:
            header = header + "\n" + preview_marker  # marker last so its \fancyhf{} wins (preview only)
        else:
            plan.pre_args += ["-V", "header-includes=" + preview_marker]
    if header:
        hpath = os.path.join(latex_dir, "layout-header.tex")
        with open(hpath, "w", encoding="utf-8") as f:
            f.write(header + "\n")
        plan.args += ["--include-in-header", "layout-header.tex"]
        plan.files["layout-header.tex"] = C.sha256_file(hpath)
    for l in lua:
        plan.args += ["--lua-filter", l]
    fm = resolve_frontmatter(dt, cfg)
    if fm:
        logo_name = None
        if fm.get("logo"):
            if not logo or not os.path.isfile(logo):
                raise ValueError("frontmatter.logo is set but no locked logo exists; run: ms_state.py lock-logo")
            logo_name = "ms-logo." + logo.rsplit(".", 1)[1].lower()
            lp = os.path.join(latex_dir, logo_name)
            shutil.copy2(logo, lp)
            plan.files[logo_name] = C.sha256_file(lp)
        mpath = os.path.join(latex_dir, "frontmatter-metadata.json")
        with open(mpath, "w", encoding="utf-8") as f:
            f.write(json.dumps(frontmatter_metadata(fm, logo_name), indent=2, sort_keys=True) + "\n")
        plan.args += ["--metadata-file", "frontmatter-metadata.json"]  # report front matter outranks these shared defaults
        plan.files["frontmatter-metadata.json"] = C.sha256_file(mpath)
    if plan.citeproc:
        plan.csl = os.path.join(skill_csl_dir(skill_dir), CITATION_STYLES[plan.citation_style]["csl"])
    return plan


def describe():
    lines = ["Layout options (project-config.yaml `layout:` map; doctype defaults < config):"]
    for k, vals in LAYOUT_KEYS.items():
        allowed = "<number>cm|mm|in" if vals is None else " | ".join(vals)
        lines.append("  %-18s %s    # %s" % (k, allowed, LAYOUT_NOTES[k]))
    lines.append("")
    lines.append("Citation styles (`citation_style:` in project-config.yaml or a doctype):")
    for k, v in CITATION_STYLES.items():
        lines.append("  %-20s %-7s %s" % (k, v["engine"], v["description"]))
    lines.append("")
    lines.append("Formal thesis front matter (doctype thesis-formal only; project-config.yaml `frontmatter:` map):")
    for k, kind in FRONTMATTER_KEYS.items():
        lines.append("  %-18s %-13s # %s" % (k, kind, FRONTMATTER_NOTES[k]))
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
