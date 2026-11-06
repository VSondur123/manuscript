#!/usr/bin/env python3
"""Write a human-readable reference list into the report's final '# References' section, for review.

Usage: render_references.py [--project ID] [--root DIR]
The .ms/references.bib file stays the source of truth. The list between the
<!-- references:start --> / <!-- references:end --> markers is generated from it (only fields that are
present are printed; nothing is invented) and is dropped when converting to LaTeX, where BibTeX builds the
real bibliography. Re-run after the bibliography or citations change. Backs up the report first.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402
import ms_state as S  # noqa: E402
from validate_references import parse_bib  # noqa: E402

START, END = "<!-- references:start -->", "<!-- references:end -->"


def clean(v):
    return re.sub(r"\s+", " ", re.sub(r"[{}]", "", v or "")).strip()


def fmt_authors(a):
    names = [n.strip() for n in re.split(r"\s+and\s+", clean(a)) if n.strip()]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1] if names else ""


def format_entry(key, e):
    f = {k: clean(v) for k, v in e["fields"].items()}
    parts = []
    who = fmt_authors(f["author"]) if f.get("author") else (fmt_authors(f["editor"]) + " (Ed.)" if f.get("editor") else "")
    if who:
        parts.append(who + ".")
    if f.get("year"):
        parts.append("(%s)." % f["year"])
    if f.get("title"):
        parts.append(f["title"] + ".")
    venue = f.get("journal") or f.get("booktitle") or f.get("publisher") or f.get("institution") or f.get("school")
    if venue:
        vol = f.get("volume", "") + ("(%s)" % f["number"] if f.get("number") else "")
        parts.append(", ".join(x for x in (venue, vol, f.get("pages")) if x) + ".")
    if f.get("doi"):
        parts.append("https://doi.org/" + re.sub(r"^https?://(dx\.)?doi\.org/", "", f["doi"]))
    elif f.get("url"):
        parts.append(f["url"])
    return "- %s *(key: %s)*" % (" ".join(parts), key)


def render(bib_text):
    entries, _ = parse_bib(bib_text)
    lines = [format_entry(k, e) for k, e in sorted(entries.items(), key=lambda kv: clean(kv[1]["fields"].get("author", kv[0])).lower())]
    return START + "\n" + "\n".join(lines) + "\n" + END, len(lines)


def update_report(text, block):
    pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if pat.search(text):
        return pat.sub(lambda m: block, text)
    text = re.sub(r"\n#{1,2}\s+(References|Bibliography)\s*\n*\Z", "\n", text).rstrip("\n")
    return text + "\n\n# References\n\n" + block + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project"); ap.add_argument("--root", default=os.getcwd())
    a = ap.parse_args(argv)
    try:
        root = os.path.abspath(a.root)
        pid = S.resolve(root, a.project)
        st = S.load(root, pid)
        report, bib = S.artifact_path(root, pid, "draft"), S.artifact_path(root, pid, "bibliography")
        if not os.path.isfile(report):
            raise S.StateError("%s-report.md does not exist yet" % pid)
        if not os.path.isfile(bib) or "@" not in C.read_text(bib):
            raise S.StateError("No bibliography entries in %s" % os.path.relpath(bib, S.pdir(root, pid)))
        block, n = render(C.read_text(bib))
        old = C.read_text(report)
        new = update_report(old, block)
        if new != old:
            print("backup: " + S.backup(root, pid, os.path.basename(report)))
            with open(report, "w", encoding="utf-8") as f:
                f.write(new)
            S.sync(root, pid, st)
            S.save(root, pid, st)
        print("%d reference(s) listed in %s" % (n, os.path.basename(report)))
        return 0
    except (S.StateError, OSError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
