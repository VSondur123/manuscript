#!/usr/bin/env python3
"""Export the APPROVED Markdown snapshot of a project to Word (.docx) with pandoc. Optional extra output, not a stage.

Refuses to run unless the Markdown approval is current (draft hash == approved hash) and the approved snapshot is
intact. Never reads the working draft. No pandoc-crossref needed: templates/docx/ms-docx.lua numbers figures, tables
and sections and rewrites "[Figure](#fig-x)" links. Citations/References use pandoc --citeproc with a vendored CSL file.

Usage: md_to_docx.py [--project ID] [--root DIR]
Output: <project>/.ms/docx/<id>.docx (+ reference.docx, log in .ms/logs/docx-generation.log). Copy it into the visible
folder only on request: ms_state.py publish --docx   (or --docx-only).
What Word cannot express (two columns, booktabs, venue/template typesetting, LaTeX fonts, ...) is listed as IGNORED.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402
import ms_state as S  # noqa: E402
import layout as L  # noqa: E402
import md_to_latex as M  # noqa: E402

SKILL_DIR = M.SKILL_DIR
FILTER = os.path.join(SKILL_DIR, "templates", "docx", "ms-docx.lua")
# BibTeX-path styles have no LaTeX-free equivalent: use official CSL files (templates/csl/NOTICE.md)
DOCX_CSL = {"numeric": "elsevier-vancouver.csl", "author-year": "elsevier-harvard.csl", "ieee": "ieee.csl"}
DOCX_FONTS = {"times": "Times New Roman", "palatino": "Palatino Linotype", "helvetica-sans": "Arial"}
PAPER_TWIPS = {"a4": (11906, 16838), "letter": (12240, 15840)}  # width, height
LINE = {"single": 240, "onehalf": 360, "double": 480}
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# ------------------------------------------------------------------ options
def margin_twips(v):
    """'2.5cm' | '25mm' | '1in' (already whitelisted by layout.py) -> twips. Raises ValueError otherwise."""
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(cm|mm|in)", v)
    if not m:
        raise ValueError("margins %r" % v)
    return int(round(float(m.group(1)) * {"cm": 566.929, "mm": 56.6929, "in": 1440}[m.group(2)]))


def is_venue(dt):
    """Doctypes with their own LaTeX template (ieee/acm/llncs/elsevier/revtex/preprint...) except the formal thesis."""
    return bool(dt.get("pandoc_template")) and not dt.get("frontmatter")


def resolve_options(dt, cfg):
    """(opts, notes, ignored). opts: paper, font_size(pt int), spacing(twips line), margins(twips), font(name|None),
    header, page_numbers, number_sections(bool), print_links(bool). All values whitelisted; nothing is free text."""
    layout = L.resolve_layout(dt, cfg)
    style = L.resolve_citation_style(dt, cfg) or "numeric"
    base = {}
    if not is_venue(dt):  # same Word defaults as the LaTeX defaults file of the doctype; venue classes get the article defaults
        p = os.path.join(SKILL_DIR, dt.get("latex_defaults", "templates/latex/article.yaml"))
        base = C.load_yaml(p) if os.path.isfile(p) else {}
    if not base:
        base = C.load_yaml(os.path.join(SKILL_DIR, "templates/latex/article.yaml"))
    v = base.get("variables") or {}
    co = v.get("classoption") or []
    co = [co] if isinstance(co, str) else co
    size = next((int(re.match(r"(\d+)", o).group(1)) for o in co if re.fullmatch(r"1[012]pt", o)), 11)
    paper = next((o[:-5] for o in co if o in ("a4paper", "letterpaper")), "a4")
    mm = re.fullmatch(r"margin=(.+)", str(v.get("geometry") or ""))
    margins = mm.group(1) if mm and L.MARGIN_RE.match(mm.group(1)) else "2.5cm"
    try:
        stretch = float(v.get("linestretch", 1.15))
    except (TypeError, ValueError):
        stretch = 1.15
    line = int(round(240 * min(max(stretch, 1.0), 3.0)))
    opts = {"paper": paper, "font_size": size, "line": line, "margins": margin_twips(margins), "font": None,
            "header": "none", "page_numbers": "bottom-center",
            "number_sections": bool(base.get("number-sections", True)), "print_links": False, "citation_style": style}
    ignored = []
    if "paper" in layout:
        opts["paper"] = layout["paper"]
    if "font_size" in layout:
        opts["font_size"] = int(layout["font_size"])
    if "spacing" in layout:
        opts["line"] = LINE[layout["spacing"]]
    if "margins" in layout:
        opts["margins"] = margin_twips(layout["margins"])
    if "font" in layout:
        if layout["font"] in DOCX_FONTS:
            opts["font"] = DOCX_FONTS[layout["font"]]
        elif layout["font"] != "cm":
            ignored.append("layout.font: %s has no default Word equivalent; Word's default font kept (set it in Word)" % layout["font"])
        else:
            ignored.append("layout.font: cm (Computer Modern) is a TeX font; Word's default font kept")
    for k in ("header", "page_numbers"):
        if k in layout:
            opts[k] = layout[k]
    if "heading_numbering" in layout:
        opts["number_sections"] = layout["heading_numbering"] == "on"
    if layout.get("colour") == "print":
        opts["print_links"] = True
    if layout.get("columns") == "2":
        ignored.append("layout.columns: 2 - Word export is single column (section columns are not generated)")
    if layout.get("caption_position") == "top":
        ignored.append("layout.caption_position: top - figure captions stay below the figure (table captions are above)")
    if "table_style" in layout:
        ignored.append("layout.table_style: %s - tables use pandoc's Word table style (no booktabs rules)" % layout["table_style"])
    if layout.get("colour") == "screen":
        pass  # Word's default blue hyperlinks are the screen look
    notes = []
    if is_venue(dt):
        notes.append("venue/template-specific typesetting (%s) is NOT reproduced in Word; generic Word styling "
                     "(article defaults) is used. Use the PDF for the venue layout or apply the publisher's Word template manually"
                     % dt.get("pandoc_template"))
    if (cfg or {}).get("template"):
        ignored.append("config 'template' is a LaTeX/pandoc template and is not used for Word")
    return opts, notes, ignored


# ------------------------------------------------------------------ reference.docx
def _fld(instr, cached):
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> %s </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>%s</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
            % (instr, escape(cached)))


def _tab():
    return "<w:r><w:tab/></w:r>"


def header_footer_xml(opts, width, title, author):
    """(header_xml|None, footer_xml|None) from whitelisted header / page_numbers values. title/author are the document's
    own metadata, XML-escaped; no config text is used."""
    head, num = opts["header"], opts["page_numbers"]
    ns = 'xmlns:w="%s"' % NS_W
    tabs = '<w:tabs><w:tab w:val="center" w:pos="%d"/><w:tab w:val="right" w:pos="%d"/></w:tabs>' % (width // 2, width)
    page = _fld("PAGE", "1")
    header = footer = None
    if head != "none" or num == "top-right":
        runs = ""
        if head == "running-title":
            runs += _fld("TITLE", title) + _tab() + _tab()
        elif head == "title-author":
            runs += _fld("AUTHOR", author) + _tab() + _fld("TITLE", title) + _tab()
        else:
            runs += _tab() + _tab()
        if num == "top-right":
            runs += page
        border = '<w:pBdr><w:bottom w:val="single" w:sz="4" w:space="1" w:color="000000"/></w:pBdr>' if head != "none" else ""
        header = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr %s><w:p><w:pPr>%s%s</w:pPr>%s</w:p></w:hdr>' % (ns, border, tabs, runs)
    if num in ("bottom-center", "bottom-right"):
        jc = "center" if num == "bottom-center" else "right"
        footer = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr %s><w:p><w:pPr><w:jc w:val="%s"/></w:pPr>%s</w:p></w:ftr>' % (ns, jc, page)
    return header, footer


def patch_styles(xml, opts):
    sz = opts["font_size"] * 2
    xml = re.sub(r'(<w:rPrDefault>.*?)<w:sz w:val="\d+"\s*/>\s*<w:szCs w:val="\d+"\s*/>',
                 lambda m: '%s<w:sz w:val="%d" /><w:szCs w:val="%d" />' % (m.group(1), sz, sz), xml, count=1, flags=re.S)
    xml = xml.replace('<w:pPrDefault>\n      <w:pPr>\n        <w:spacing w:after="200" />',
                      '<w:pPrDefault>\n      <w:pPr>\n        <w:spacing w:after="200" w:line="%d" w:lineRule="auto" />' % opts["line"], 1)
    if opts["font"]:
        f = escape(opts["font"], {'"': "&quot;"})
        xml = re.sub(r'<w:rFonts\s+w:asciiTheme="[^"]*"[^>]*/>', '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s" />' % (f, f, f), xml)
    if opts["print_links"]:
        xml = xml.replace('<w:color w:val="4F81BD" w:themeColor="accent1" />', '<w:color w:val="000000" />', 1)
    cover = ('<w:style w:type="paragraph" w:customStyle="1" w:styleId="CoverLine"><w:name w:val="Cover Line"/>'
             '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="60" w:after="60"/><w:jc w:val="center"/></w:pPr></w:style>')
    return xml.replace("</w:styles>", cover + "</w:styles>", 1)


def build_reference_docx(path, opts, title="", author=""):
    """Write a Word reference document (pandoc's default, patched) to `path`. Raises RuntimeError if pandoc is unusable."""
    r = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("pandoc could not provide its default reference.docx: " + r.stderr.decode("utf-8", "replace"))
    src = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    try:
        src.write(r.stdout)
        src.close()
        with zipfile.ZipFile(src.name) as z:
            parts = {i.filename: z.read(i.filename) for i in z.infolist()}
    finally:
        os.unlink(src.name)
    w, h = PAPER_TWIPS[opts["paper"]]
    m = opts["margins"]
    width = w - 2 * m
    parts["word/styles.xml"] = patch_styles(parts["word/styles.xml"].decode("utf-8"), opts).encode("utf-8")
    hdr, ftr = header_footer_xml(opts, width, title, author)
    refs = ""
    rels = parts["word/_rels/document.xml.rels"].decode("utf-8")
    ctypes = parts["[Content_Types].xml"].decode("utf-8")
    for tag, name, xml, ctype, rid in (("header", "header1.xml", hdr, "header", "rIdMsHdr"), ("footer", "footer1.xml", ftr, "footer", "rIdMsFtr")):
        if xml is None:
            continue
        parts["word/" + name] = xml.encode("utf-8")
        rels = rels.replace("</Relationships>", '<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/%s" Target="%s"/></Relationships>' % (rid, tag, name))
        ctypes = ctypes.replace("</Types>", '<Override PartName="/word/%s" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.%s+xml"/></Types>' % (name, ctype))
        refs += '<w:%sReference w:type="default" r:id="%s"/>' % (tag, rid)
    parts["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    parts["[Content_Types].xml"] = ctypes.encode("utf-8")
    sect = ('<w:sectPr>%s<w:footnotePr><w:numRestart w:val="eachSect" /></w:footnotePr><w:pgSz w:w="%d" w:h="%d"/>'
            '<w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d" w:header="%d" w:footer="%d" w:gutter="0"/></w:sectPr>'
            % (refs, w, h, m, m, m, m, min(720, m // 2), min(720, m // 2)))
    doc = parts["word/document.xml"].decode("utf-8")
    doc2 = re.sub(r"<w:sectPr>.*?</w:sectPr>", lambda _m: sect, doc, count=1, flags=re.S)
    if doc2 == doc:
        raise RuntimeError("pandoc's reference.docx has no sectPr to patch (unsupported pandoc version)")
    parts["word/document.xml"] = doc2.encode("utf-8")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:  # fixed timestamps: identical options -> identical bytes
        order = ["[Content_Types].xml"] + sorted(k for k in parts if k != "[Content_Types].xml")
        for k in order:
            zi = zipfile.ZipInfo(k, (2000, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, parts[k])
    return path


# ------------------------------------------------------------------ helpers
def inlines_text(inl):
    out = []
    for x in inl or []:
        t = x.get("t")
        if t == "Str":
            out.append(x["c"])
        elif t in ("Space", "SoftBreak", "LineBreak"):
            out.append(" ")
        elif isinstance(x.get("c"), list):
            for y in x["c"]:
                if isinstance(y, list) and y and isinstance(y[0], dict):
                    out.append(inlines_text(y))
    return "".join(out)


def meta_text(m):
    if not m:
        return ""
    t, c = m.get("t"), m.get("c")
    if t in ("MetaInlines",):
        return inlines_text(c)
    if t == "MetaString":
        return c
    if t == "MetaList":
        return ", ".join(meta_text(x) for x in c)
    if t == "MetaBlocks":
        return " ".join(inlines_text(b.get("c")) for b in c if isinstance(b.get("c"), list))
    return ""


def pdf_to_png(text, d, locked=None):
    """Word cannot embed PDF figures: use the sibling .png (build_figures.py writes both). Returns (text, log).
    `locked` = the approval's {path: sha256} figure map: a substituted PNG must be hash-locked there and unchanged."""
    log = []

    def sub(m):
        rel = m.group(2)
        if re.match(r"^[a-z]+://", rel) or not rel.lower().endswith(".pdf"):
            return m.group(0)
        png = rel[:-4] + ".png"
        if os.path.isfile(os.path.join(d, png)):
            if locked is not None and locked.get(os.path.normpath(png)) != C.sha256_file(os.path.join(d, png)):
                raise S.StateError("Figure %s is a PDF; its sibling %s replaces it in Word but is not covered by the Markdown approval "
                                   "(missing or changed since approval). Re-approve the Markdown to lock it." % (rel, png))
            log.append("figure %s -> %s (Word cannot embed PDF figures; the sibling PNG is hash-locked by the approval)" % (rel, png))
            return m.group(1) + png
        raise S.StateError("Figure %s is a PDF and has no .png sibling; Word needs a raster/SVG image" % rel)
    return re.sub(r"(!\[[^\]]*\]\()([^)\s]+)", sub, text), log


def export(root, pid):
    """Run the export; returns (docx_path, log lines, ignored, notes). Raises S.StateError on refusal/failure."""
    st = S.load(root, pid)
    d = S.pdir(root, pid)
    if S.markdown_approval_status(root, pid, st) != "current":
        raise S.StateError("Markdown is not currently approved (never approved, or draft changed). Get 'APPROVE MARKDOWN' first.")
    drift = [c for c in S.verify(root, pid, st) if c["artifact"] == "approved"]
    if drift:
        raise S.StateError("Approved snapshot problem: %s" % drift[0]["detail"])
    if not C.which("pandoc"):
        raise S.StateError("pandoc not installed (brew install pandoc)")
    ap_rec = st["markdown_approval"]
    snap = os.path.join(d, ap_rec["snapshot"])
    cfg, dt = M.load_context(root, pid, st)
    try:
        opts, notes, ignored = resolve_options(dt, cfg)
        fm = L.resolve_frontmatter(dt, cfg)
    except ValueError as e:
        raise S.StateError(str(e))
    out_dir = os.path.join(d, S.WORK, "docx")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(d, S.WORK, "logs"), exist_ok=True)
    with_bib = M.has_bibliography(root, pid)
    text, log = M.prepare_markdown(C.read_text(snap), citeproc=with_bib)
    text, l2 = pdf_to_png(text, d, ap_rec.get("figures") or {})
    log += l2
    for m in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)", text):
        rel = m.group(1)
        if not re.match(r"^[a-z]+://", rel) and not os.path.isfile(os.path.normpath(os.path.join(d, rel))):
            raise S.StateError("Figure file missing: %s" % rel)
    csl = None
    if with_bib:
        style = opts["citation_style"]
        name = L.CITATION_STYLES[style].get("csl") if L.CITATION_STYLES[style]["engine"] == "csl" else DOCX_CSL[style]
        csl = os.path.join(L.skill_csl_dir(SKILL_DIR), name)
        if not os.path.isfile(csl):
            raise S.StateError("CSL file missing: templates/csl/%s" % name)
        if style in DOCX_CSL:
            notes.append("citation_style %s uses BibTeX in the PDF but the CSL file %s in Word: the Word reference list and citation "
                         "order/format may differ from the PDF" % (style, name))
    elif re.search(r"(?<![\w@])@[A-Za-z]|\[@", text):
        log.append("warning: text has citations but the project has no bibliography entries")
    tmp_md = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, dir=out_dir, encoding="utf-8")
    try:
        tmp_md.write(text)
        tmp_md.close()
        r = subprocess.run(["pandoc", "-f", "markdown-raw_tex-raw_attribute", "-t", "json", tmp_md.name], capture_output=True, text=True, cwd=d)
        meta = json.loads(r.stdout).get("meta", {}) if r.returncode == 0 else {}
        ref = build_reference_docx(os.path.join(out_dir, "reference.docx"), opts, meta_text(meta.get("title")), meta_text(meta.get("author")))
        cmd = ["pandoc", "-f", "markdown-raw_tex-raw_attribute", "-t", "docx", "--reference-doc", ref, "--lua-filter", FILTER,
               "-M", "ms-number-sections=%s" % ("true" if opts["number_sections"] else "false")]
        if opts["number_sections"]:
            cmd.append("--number-sections")
        if with_bib:
            # (MLA: link-citations turns an author-only narrative cite into "Lee ()")
            cmd += ["--citeproc"] + ([] if opts["citation_style"] == "mla9" else ["-M", "link-citations=true"]) + ["--bibliography", S.artifact_path(root, pid, "bibliography"), "--csl", csl]
        if fm or dt.get("frontmatter"):
            md = L.frontmatter_metadata(fm)
            mpath = os.path.join(out_dir, "frontmatter-metadata.json")
            with open(mpath, "w", encoding="utf-8") as f:
                f.write(json.dumps({k: v for k, v in md.items() if isinstance(v, (str, list))
                                    and k in ("institution", "faculty", "department", "degree", "supervisor", "date")}, indent=2, sort_keys=True) + "\n")
            cmd += ["--metadata-file", mpath]
            if fm.get("toc", True):
                cmd += ["--toc", "--toc-depth=3"]
            notes.append("thesis-formal: the LaTeX cover page, roman front-matter numbering and lettered appendices are NOT reproduced in Word; "
                         "Word gets title/author/date, cover lines, abstract and a table of contents (a Word field: right-click > Update field if it shows no entries)")
            for k, what in (("lof", "list of figures"), ("lot", "list of tables"), ("roman_front_matter", "roman front-matter page numbers"),
                            ("logo", "cover logo"), ("declaration", "declaration page"), ("copyright", "copyright page"),
                            ("dedication", "dedication"), ("acknowledgements", "acknowledgements page")):
                if fm.get(k):
                    ignored.append("frontmatter.%s (%s) is not reproduced in Word" % (k, what))
            log.append("thesis front matter: title, author, date, abstract, cover lines (degree/department/faculty/institution/supervisor) "
                       "and %s are emitted" % ("a table of contents" if fm.get("toc", True) else "no table of contents"))
        out_name = "%s.docx" % pid
        tmp_out = os.path.join(out_dir, out_name + ".tmp")
        r = subprocess.run(cmd + ["-o", tmp_out, tmp_md.name], cwd=d, capture_output=True, text=True)
    finally:
        os.unlink(tmp_md.name)
    if r.returncode != 0:
        if os.path.isfile(tmp_out):
            os.unlink(tmp_out)
        raise S.StateError("pandoc failed:\n%s" % r.stderr)
    unresolved = sorted({m.group(1) for m in re.finditer(r"^MS-UNRESOLVED-REF (\S+)$", r.stderr, flags=re.M)})
    warn = "\n".join(l for l in r.stderr.splitlines() if l.strip() and not l.startswith("MS-UNRESOLVED-REF"))
    if unresolved:
        os.unlink(tmp_out)
        raise S.StateError("unresolved cross-reference link(s): %s (no matching figure/table/section id)" % ", ".join("#" + u for u in unresolved))
    if warn:
        log.append("pandoc warnings: " + warn.replace("\n", " | "))
    docx = os.path.join(out_dir, out_name)
    os.replace(tmp_out, docx)
    return docx, cmd, log, ignored, notes, opts, csl, st, ap_rec, unresolved


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project"); ap.add_argument("--root", default=os.getcwd())
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    try:
        pid = S.resolve(root, a.project)
        docx, cmd, log, ignored, notes, opts, csl, st, ap_rec, unresolved = export(root, pid)
        d = S.pdir(root, pid)
        import validate_docx as V
        res = V.validate(docx, C.read_text(os.path.join(d, ap_rec["snapshot"])))
        rec = {"path": os.path.relpath(docx, d), "sha256": C.sha256_file(docx), "from_approved_sha256": ap_rec["sha256"],
               "version": (st.get("docx") or {}).get("version", 0) + 1, "generated_at": C.now(),
               "inputs": {"citation_style": opts["citation_style"], "ignored": ignored, "notes": notes,
                          "reference_docx": C.sha256_file(os.path.join(d, S.WORK, "docx", "reference.docx")),
                          "filter": C.sha256_file(FILTER)}}
        if csl:
            rec["inputs"]["csl"] = {"path": os.path.relpath(csl, SKILL_DIR), "sha256": C.sha256_file(csl)}
        with open(os.path.join(d, S.WORK, "logs", "docx-generation.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(["generated_at: " + C.now(), "source: " + ap_rec["snapshot"], "command: " + " ".join(cmd)] + log
                              + ["IGNORED: " + i for i in ignored] + ["NOTE: " + n for n in notes]
                              + ["VALIDATION %s: %s" % (k.upper(), m) for k in ("errors", "warnings") for m in res[k]]) + "\n")
        print("Wrote %s" % docx)
        for l in log:
            print(" - " + l)
        for n in notes:
            print(" NOTE: " + n)
        for i in ignored:
            print(" IGNORED: " + i)
        for w in res["warnings"]:
            print(" WARN: " + w)
        if res["errors"]:
            for e in res["errors"]:
                print(" ERROR: " + e, file=sys.stderr)
            print("DOCX validation failed; state not updated.", file=sys.stderr)
            return 1
        st["docx"] = rec
        S.save(root, pid, st)
        print("DOCX validated (%d headings, %d citations resolved, %d images). Publish on request: ms_state.py publish --docx-only"
              % (res["stats"]["headings"], res["stats"]["citations"], res["stats"]["images"]))
        return 0
    except (S.StateError, OSError, ValueError, RuntimeError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
