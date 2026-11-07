#!/usr/bin/env python3
"""Check an exported .docx against the Markdown it was made from (no Word needed; stdlib zipfile + xml).

Usage: validate_docx.py FILE.docx [--markdown FILE.md | --project ID [--root DIR]]
  With --project the APPROVED snapshot is the reference (never the working draft). Without a Markdown reference only
  the structural checks run. Exit 0 ok, 1 errors, 2 usage.
Checks: zip and every XML part well-formed; title, abstract and every Markdown heading present (as Word headings);
no leftover citation markup ('(?)', '[@key', '@key', '??'); the reference list has an entry per cited key;
images embedded (Markdown images == drawings, media parts present); no unresolved cross-reference placeholders and
every internal hyperlink has its bookmark; tables and math present when the Markdown has them; no [[EVIDENCE NEEDED]].
validate(path, md_text=None) -> {"errors": [...], "warnings": [...], "stats": {...}} for programmatic use.
"""
import argparse
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def strip_code(md):
    md = re.sub(r"^(```|~~~).*?^\1[^\n]*$", "", md, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "", md)


def md_facts(md):
    """title, abstract, headings, cited keys, image count, table count, has_math from Markdown text."""
    title = abstract = ""
    body = md
    m = re.match(r"---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", md, flags=re.S)
    if m:
        fm, body = m.group(1), md[m.end():]
        t = re.search(r"^title:\s*(.+)$", fm, flags=re.M)
        if t:
            title = t.group(1).strip().strip("\"'")
        a = re.search(r"^abstract:\s*[|>][-+]?\s*\n((?:[ \t]+.*\n?)+)", fm, flags=re.M)
        if a:
            abstract = " ".join(l.strip() for l in a.group(1).splitlines())
        else:
            a = re.search(r"^abstract:\s*(.+)$", fm, flags=re.M)
            if a:
                abstract = a.group(1).strip().strip("\"'")
    code_free = strip_code(body)
    headings = []
    for h in re.finditer(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", code_free, flags=re.M):
        t = re.sub(r"[ \t]*\{[^}]*\}\s*$", "", h.group(2))
        t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
        if "$" in t or "<!--" in t:
            continue
        headings.append(re.sub(r"[*_]", "", t))
    nocomment = re.sub(r"<!--.*?-->", "", code_free, flags=re.S)
    keys = set(re.findall(r"(?<![\w.@])@([A-Za-z0-9_][A-Za-z0-9_:.+/-]*[A-Za-z0-9_]|[A-Za-z0-9_])", nocomment))
    keys = {k for k in keys if not re.match(r"^(fig|tbl|sec|eq|lst)[-:]", k)}
    images = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", nocomment))
    tables = len(re.findall(r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)+\|?[ \t]*$", nocomment, flags=re.M))
    math = bool(re.search(r"\$\$.+?\$\$", nocomment, flags=re.S))
    return {"title": title, "abstract": abstract, "headings": headings, "keys": keys, "images": images, "tables": tables, "math": math}


def paragraphs(root):
    """[(style, text)] for every paragraph (body and tables)."""
    out = []
    for p in root.iter(W + "p"):
        st = p.find("%spPr/%spStyle" % (W, W))
        style = st.get(W + "val") if st is not None else ""
        parts = []
        for n in p.iter():
            if n.tag == W + "t" and n.text:
                parts.append(n.text)
            elif n.tag in (W + "tab", W + "br"):
                parts.append(" ")
        out.append((style, "".join(parts)))
    return out


def validate(path, md_text=None):
    errors, warnings = [], []
    stats = {"headings": 0, "citations": 0, "images": 0, "tables": 0, "paragraphs": 0}
    res = {"errors": errors, "warnings": warnings, "stats": stats}
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        errors.append("not a readable .docx (zip) file: %s" % e)
        return res
    with z:
        bad = z.testzip()
        if bad:
            errors.append("corrupt zip member: %s" % bad)
        names = z.namelist()
        trees = {}
        for n in names:
            if n.endswith(".xml") or n.endswith(".rels"):
                try:
                    trees[n] = ET.fromstring(z.read(n))
                except ET.ParseError as e:
                    errors.append("XML part not well-formed: %s (%s)" % (n, e))
        for need in ("[Content_Types].xml", "word/document.xml"):
            if need not in names:
                errors.append("missing part: " + need)
        if "word/document.xml" not in trees:
            return res
        doc = trees["word/document.xml"]
        paras = paragraphs(doc)
        stats["paragraphs"] = len(paras)
        head_texts = [t for s, t in paras if re.match(r"(?i)heading\d|^Heading", s or "")]
        stats["headings"] = len(head_texts)
        full = " ".join(t for _, t in paras)
        stats["tables"] = len(list(doc.iter(W + "tbl")))
        draw = len(list(doc.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline"))) + \
            len(list(doc.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}anchor")))
        stats["images"] = draw
        media = [n for n in names if n.startswith("word/media/")]
        for rel in trees.get("word/_rels/document.xml.rels", []):
            if rel.get("Type", "").endswith("/image") and "word/" + rel.get("Target", "") not in names:
                errors.append("image relationship points to a missing part: %s" % rel.get("Target"))
        if draw and not media:
            errors.append("document has drawings but no word/media parts")
        # leftovers that mean the conversion did not finish
        for pat, what in ((r"\(\?\)|\?\?", "unresolved citation/reference marker ('(?)' or '??')"),
                          (r"\[@|@[A-Za-z][\w:-]*\d", "raw citation key left in the text (e.g. '[@key' or '@key2020')"),
                          (r"\{#[\w:-]+\}|\]\(#[\w:-]+\)|\(#(?:fig|tbl|sec|eq)[\w:-]*\)", "unresolved cross-reference/attribute markup ('{#id}' or '](#id)')"),
                          (r"\[\[EVIDENCE NEEDED", "[[EVIDENCE NEEDED]] placeholder")):
            m = re.search(pat, full)
            if m:
                errors.append("%s: %r" % (what, full[max(0, m.start() - 30):m.end() + 30]))
        bookmarks = {b.get(W + "name") for b in doc.iter(W + "bookmarkStart")}
        for h in doc.iter(W + "hyperlink"):
            a = h.get(W + "anchor")
            if a and a not in bookmarks:
                errors.append("internal link to missing bookmark %r (unresolved cross-reference?)" % a)
        if md_text is None:
            return res
        f = md_facts(md_text)
        if f["title"] and norm(f["title"]) not in norm(" ".join(t for s, t in paras if s == "Title") or full):
            errors.append("title missing in the Word document: %r" % f["title"])
        if f["abstract"]:
            probe = norm(f["abstract"])[:60]
            if probe not in norm(full):
                errors.append("abstract text missing in the Word document")
        # pandoc --number-sections writes a literal '1.2 ' prefix: strip it, then compare exactly
        have_plain = {norm(re.sub(r"^\s*\d+(?:\.\d+)*\s+", "", t)) for t in head_texts}
        for h in f["headings"]:
            if norm(h) and norm(h) not in have_plain:
                errors.append("heading missing (or not a Word heading): %r" % h)
        # citations
        keys = sorted(f["keys"])
        stats["citations"] = len(keys)
        left = [k for k in keys if re.search(r"@%s(?![\w])" % re.escape(k), full)]
        for k in left:
            errors.append("citation @%s not resolved" % k)
        bib = [t for s, t in paras if s == "Bibliography"]
        if keys and not bib:
            errors.append("document cites %d source(s) but has no reference list (Bibliography paragraphs)" % len(keys))
        elif keys and len(bib) < len(keys):
            warnings.append("reference list has %d entries for %d cited keys" % (len(bib), len(keys)))
        # figures / tables / math
        if f["images"] > draw:
            errors.append("Markdown has %d image(s) but the Word document embeds %d" % (f["images"], draw))
        if f["tables"] > stats["tables"]:
            errors.append("Markdown has %d table(s) but the Word document has %d" % (f["tables"], stats["tables"]))
        if f["math"] and not list(doc.iter(MATH + "oMath")) and not list(doc.iter(MATH + "oMathPara")):
            errors.append("Markdown has display math but the Word document has no equation objects")
        want = len(re.findall(r"(?<!!)\[(?:Figure|Fig\.|Table|Tab\.)\]\(#[^)\s]+\)", strip_code(md_text)))
        got = 0
        for h in doc.iter(W + "hyperlink"):
            if h.get(W + "anchor") and re.fullmatch(r"(?:Figure|Fig\.|Table|Tab\.)\xa0\d+", "".join(t.text or "" for t in h.iter(W + "t"))):
                got += 1
        if got < want:
            errors.append("%d Figure/Table cross-reference link(s) in the Markdown but only %d resolved to 'Figure N'/'Table N' in Word" % (want, got))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx")
    ap.add_argument("--markdown")
    ap.add_argument("--project"); ap.add_argument("--root", default=os.getcwd())
    a = ap.parse_args(argv)
    if not os.path.isfile(a.docx):
        print(__doc__)
        return 2
    md = None
    if a.markdown:
        md = open(a.markdown, encoding="utf-8").read()
    elif a.project:
        import ms_state as S
        root = os.path.abspath(a.root)
        st = S.load(root, S.resolve(root, a.project))
        ap_rec = st.get("markdown_approval")
        if not ap_rec:
            print("ERROR: no approved Markdown snapshot to compare with", file=sys.stderr)
            return 2
        md = open(os.path.join(S.pdir(root, a.project), ap_rec["snapshot"]), encoding="utf-8").read()
    res = validate(a.docx, md)
    print("%d errors, %d warnings; %s" % (len(res["errors"]), len(res["warnings"]), ", ".join("%s=%s" % kv for kv in res["stats"].items())))
    for e in res["errors"]:
        print("ERROR " + e)
    for w in res["warnings"]:
        print("WARN  " + w)
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
