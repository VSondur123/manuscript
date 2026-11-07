#!/usr/bin/env python3
"""Static pre-compile checks for a generated .tex file (no TeX engine required).

Usage: validate_latex.py file.tex
Checks: figure files, \\label/\\ref consistency, \\cite keys vs .bib, \\bibliography file,
begin/end balance, brace balance, leftover placeholders. Exit 0 ok, 1 errors, 2 usage.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402
from validate_references import parse_bib  # noqa: E402


def check(path):
    base = os.path.dirname(os.path.abspath(path))
    raw = C.read_text(path)
    tex = re.sub(r"(?<!\\)%.*", "", raw)
    errors, warnings = [], []
    for g in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex):
        cands = [g] + [g + e for e in (".pdf", ".png", ".jpg", ".jpeg")]
        if not any(os.path.isfile(os.path.join(base, c)) for c in cands):
            errors.append("missing figure file: %s" % g)
    labels = set(re.findall(r"\\label\{([^}]+)\}", tex))
    for m in re.finditer(r"\\(?:ref|eqref|autoref|pageref)\{([^}]+)\}", tex):
        if m.group(1) not in labels:
            errors.append("reference to undefined label: %s" % m.group(1))
    for m in re.finditer(r"\\hyperref\[([^\]]+)\]", tex):
        if m.group(1) not in labels:
            errors.append("hyperref to undefined label: %s" % m.group(1))
    bibs = re.findall(r"\\bibliography\{([^}]+)\}", tex)
    entries = {}
    # citeproc output (CSL citation styles): the reference list is built by pandoc inside the .tex;
    # citations are \citeproc{ref-KEY}{text} and entries are \bibitem[...]{ref-KEY}. Keys resolve via the .bib next to the .tex.
    if re.search(r"\\begin\{CSLReferences\}", tex):
        if bibs:
            errors.append("document mixes citeproc (CSLReferences) and \\bibliography; use one bibliography engine")
        bp = os.path.join(base, "references.bib")
        if os.path.isfile(bp):
            entries.update(parse_bib(C.read_text(bp))[0])
        items = set(re.findall(r"\\bibitem\[[^\]]*\]\{ref-([^}]+)\}", tex))
        for k in sorted(set(re.findall(r"\\citeproc\{ref-([^}]+)\}", tex))):
            if k not in entries:
                errors.append("citation key not in bibliography: %s" % k)
            elif k not in items:
                errors.append("citation %s has no entry in the generated reference list" % k)
        for k in sorted(items):
            if entries and k not in entries:
                errors.append("reference list entry not in bibliography file: %s" % k)
        bibs = ["(citeproc)"]
        cites = set()
    else:
        cites = None
    for b in [x.strip() for g in bibs for x in g.split(",")]:
        if b == "(citeproc)":
            continue
        bp = os.path.join(base, b if b.endswith(".bib") else b + ".bib")
        if not os.path.isfile(bp):
            errors.append("bibliography file not found: %s" % b)
        else:
            entries.update(parse_bib(C.read_text(bp))[0])
    if cites is None:
        cites = {k.strip() for g in re.findall(r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear|nocite)\*?(?:\[[^\]]*\])*\{([^}]*)\}", tex) for k in g.split(",")}
        cites.discard("*")
    if cites and not bibs:
        errors.append("citations present but no \\bibliography{...} in the document")
    for k in sorted(cites):
        if bibs and k not in entries:
            errors.append("citation key not in bibliography: %s" % k)
    for env in set(re.findall(r"\\begin\{([^}]+)\}", tex)) | set(re.findall(r"\\end\{([^}]+)\}", tex)):
        if len(re.findall(r"\\begin\{%s\}" % re.escape(env), tex)) != len(re.findall(r"\\end\{%s\}" % re.escape(env), tex)):
            errors.append("unbalanced environment: %s" % env)
    body = re.sub(r"\\[{}]", "", tex)
    if body.count("{") != body.count("}"):
        errors.append("unbalanced braces (%d open, %d close)" % (body.count("{"), body.count("}")))
    if re.search(r"\[\[|\bTODO\b|\bFIXME\b", tex):
        errors.append("unresolved placeholder text in LaTeX")
    if "\\begin{document}" not in tex:
        errors.append("no \\begin{document}")
    if not C.which("tectonic") and not C.which("latexmk") and not C.which("xelatex") and not C.which("pdflatex"):
        warnings.append("no LaTeX engine installed; cannot compile")
    return errors, warnings


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not os.path.isfile(argv[0]):
        print(__doc__)
        return 2
    errors, warnings = check(argv[0])
    print("%d errors, %d warnings" % (len(errors), len(warnings)))
    for e in errors:
        print("ERROR " + e)
    for w in warnings:
        print("WARN  " + w)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
