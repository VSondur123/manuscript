#!/usr/bin/env python3
"""Read-only project discovery. Inventories files and extracts text WITHOUT executing anything.

Usage: discover.py [--root DIR] [--out FILE] [--max-chars N]
Writes JSON (default: stdout) and prints a human summary to stderr.
Skips: .git, node_modules, .claude, manuscript/ (workspaces), output/, hidden dirs, symlinked dirs.
Source code is only read as text; nothing found in the repository is ever run.
"""
import argparse
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402

SKIP_DIRS = {".git", "node_modules", ".claude", "manuscript", "output", "__pycache__", ".venv", "venv", ".idea", ".vscode"}
KINDS = {
    "markdown": {".md", ".markdown"}, "text": {".txt", ".rst"}, "pdf": {".pdf"}, "docx": {".docx"},
    "latex": {".tex"}, "bibtex": {".bib"}, "table": {".csv", ".tsv"}, "spreadsheet": {".xlsx", ".xls", ".ods"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".svg", ".eps", ".tiff", ".webp"},
    "code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".r", ".m", ".ipynb", ".sh", ".sql", ".ipy"},
    "data": {".json", ".yaml", ".yml", ".xml", ".toml"},
    "presentation": {".pptx", ".ppt"},
}
EXT2KIND = {e: k for k, v in KINDS.items() for e in v}
GUIDELINE_RE = re.compile(r"assign|guideline|rubric|brief|requirement|instruction|specification|syllabus|template|marking", re.I)
TEXT_KINDS = {"markdown", "text", "latex", "bibtex", "table", "code", "data"}


def extract_text(path, kind, limit):
    """Return (text, method, limitation). Never raises."""
    try:
        if kind in TEXT_KINDS:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(limit), "read", None
        if kind == "pdf":
            if not C.which("pdftotext"):
                return "", None, "pdftotext (poppler) not installed; PDF text not extracted"
            r = subprocess.run(["pdftotext", "-layout", "-l", "50", path, "-"], capture_output=True, timeout=60)
            txt = r.stdout.decode("utf-8", "replace")
            if r.returncode != 0:
                return "", None, "pdftotext failed: %s" % r.stderr.decode("utf-8", "replace")[:120]
            if len(txt.strip()) < 20:
                return txt[:limit], "pdftotext", "little/no text; likely scanned (OCR not available)"
            return txt[:limit], "pdftotext", None
        if kind == "docx":
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
            xml = re.sub(r"</w:p>", "\n", xml)
            return re.sub(r"<[^>]+>", "", xml)[:limit], "docx-xml", "tables/figures/comments not extracted"
    except Exception as e:  # noqa: BLE001 - discovery must be resilient
        return "", None, "extraction failed: %s" % e
    return "", None, (None if kind == "image" else "no extractor for this file type")


def describe(path, kind, text):
    info = {}
    if kind == "markdown":
        info["headings"] = [l.lstrip("#").strip() for l in C.strip_code(text).splitlines() if re.match(r"^#{1,4}\s", l)][:30]
        info["images"] = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", text)[:30]
        info["citation_keys"] = sorted(set(re.findall(r"(?<![\w@])@([A-Za-z][\w:\-]+)", text)))[:30]
    elif kind == "latex":
        info["headings"] = re.findall(r"\\(?:chapter|section|subsection)\*?\{([^}]*)\}", text)[:30]
        info["citation_keys"] = sorted({k.strip() for g in re.findall(r"\\cite\w*\{([^}]*)\}", text) for k in g.split(",")})[:30]
    elif kind == "bibtex":
        info["entry_keys"] = re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", text)
    elif kind == "table":
        first = text.splitlines()[0] if text else ""
        info["header"] = first[:200]
        info["approx_rows"] = text.count("\n")
    elif kind == "code":
        info["lines"] = text.count("\n") + 1
        info["note"] = "read as text only; never executed"
    return info


def discover(root, max_chars=20000):
    root = os.path.abspath(root)
    files, inaccessible, skipped = [], [], []
    for dp, dns, fns in os.walk(root, followlinks=False):
        keep = []
        for d in sorted(dns):
            full = os.path.join(dp, d)
            if d in SKIP_DIRS or d.startswith(".") or os.path.islink(full):
                skipped.append(os.path.relpath(full, root))
            else:
                keep.append(d)
        dns[:] = keep
        for fn in sorted(fns):
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root)
            if fn.startswith("."):
                continue
            if os.path.islink(full):
                skipped.append(rel + " (symlink)")
                continue
            ext = os.path.splitext(fn)[1].lower()
            kind = EXT2KIND.get(ext, "other")
            try:
                size = os.path.getsize(full)
                digest = C.sha256_file(full)
            except OSError as e:
                inaccessible.append({"path": rel, "reason": str(e)})
                continue
            text, method, limit = extract_text(full, kind, max_chars)
            entry = {"path": rel, "kind": kind, "size": size, "sha256": digest,
                     "extraction": method, "extraction_limitation": limit,
                     "likely_requirements_doc": bool(GUIDELINE_RE.search(fn) or (kind in ("markdown", "text", "pdf", "docx") and GUIDELINE_RE.search(text[:600]))),
                     "details": describe(full, kind, text), "excerpt": re.sub(r"\s+", " ", text[:300]).strip()}
            files.append(entry)
    by_hash = {}
    for f in files:
        by_hash.setdefault(f["sha256"], []).append(f["path"])
    dups = [v for v in by_hash.values() if len(v) > 1]
    by_stem = {}
    for f in files:
        if f["kind"] in ("markdown", "text", "docx", "pdf", "latex"):
            by_stem.setdefault(os.path.splitext(os.path.basename(f["path"]))[0].lower(), []).append(f["path"])
    overlaps = [v for v in by_stem.values() if len(v) > 1 and v not in dups]
    # references to images that do not exist
    existing = {f["path"] for f in files}
    missing = []
    for f in files:
        for img in f["details"].get("images", []):
            if not re.match(r"^[a-z]+://", img):
                p = os.path.normpath(os.path.join(os.path.dirname(f["path"]), img))
                if p not in existing:
                    missing.append({"referenced_from": f["path"], "missing": img})
    counts = {}
    for f in files:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    return {
        "root": root, "discovered_at": C.now(), "counts": counts, "files": files,
        "exact_duplicates": dups, "same_name_different_format": overlaps,
        "requirements_candidates": [f["path"] for f in files if f["likely_requirements_doc"]],
        "missing_referenced_files": missing, "inaccessible": inaccessible, "skipped": skipped,
        "extraction_limitations": [{"path": f["path"], "limitation": f["extraction_limitation"]} for f in files if f["extraction_limitation"]],
        "tools": {t: bool(C.which(t)) for t in ("pdftotext", "pandoc", "tectonic", "latexmk", "pdflatex", "xelatex")},
        "primary_vs_secondary": "NOT DETERMINED by script: ask the user / judge from content (see references/evidence-management.md)",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.getcwd()); ap.add_argument("--out"); ap.add_argument("--max-chars", type=int, default=20000)
    a = ap.parse_args(argv)
    if not os.path.isdir(a.root):
        print("ERROR: not a directory: %s" % a.root, file=sys.stderr)
        return 2
    res = discover(a.root, a.max_chars)
    if a.out:
        C.write_json(a.out, res)
    else:
        import json
        print(json.dumps(res, indent=2))
    c = res["counts"]
    C.eprint("Discovery: %d files (%s)" % (len(res["files"]), ", ".join("%s=%d" % kv for kv in sorted(c.items())) or "none"))
    C.eprint("Requirements candidates: %s" % (res["requirements_candidates"] or "none"))
    C.eprint("Duplicates: %d · inaccessible: %d · extraction limitations: %d · missing referenced files: %d" % (
        len(res["exact_duplicates"]), len(res["inaccessible"]), len(res["extraction_limitations"]), len(res["missing_referenced_files"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
