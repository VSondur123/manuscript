#!/usr/bin/env python3
"""Validate a BibTeX file (stdlib parser) and optionally cross-check citations in a Markdown/LaTeX file.

Usage: validate_references.py refs.bib [--cited-in draft.md ...]
Exit codes: 0 ok, 1 errors, 2 usage/IO problem. Never invents or repairs metadata.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402

REQUIRED = {
    "article": ["author", "title", "journal", "year"],
    "book": ["author|editor", "title", "publisher", "year"],
    "inproceedings": ["author", "title", "booktitle", "year"],
    "conference": ["author", "title", "booktitle", "year"],
    "incollection": ["author", "title", "booktitle", "publisher", "year"],
    "phdthesis": ["author", "title", "school", "year"],
    "mastersthesis": ["author", "title", "school", "year"],
    "techreport": ["author", "title", "institution", "year"],
    "misc": ["title"],
    "online": ["title", "url"],
    "unpublished": ["author", "title", "note"],
}
SUSPECT = re.compile(r"^\s*(unknown|n/?a|tbd|todo|anonymous|\?+|xxx)\s*$", re.I)


def parse_bib(text):
    """Return ({key: {'type':..., 'line':..., 'fields': {...}}}, [duplicate (key,line)])."""
    entries, dups = {}, []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        etype, key = m.group(1).lower(), m.group(2)
        if etype in ("comment", "string", "preamble"):
            continue
        # find matching closing brace
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[m.end():i - 1]
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*", body):
            j = fm.end()
            if j >= len(body):
                continue
            if body[j] == "{":
                d, k = 1, j + 1
                while k < len(body) and d:
                    d += {"{": 1, "}": -1}.get(body[k], 0)
                    k += 1
                val = body[j + 1:k - 1]
            elif body[j] == '"':
                k = body.find('"', j + 1)
                val = body[j + 1:k] if k != -1 else ""
            else:
                mm = re.match(r"[^,\n]*", body[j:])
                val = mm.group(0).strip()
            fields.setdefault(fm.group(1).lower(), val.strip())
        line = text.count("\n", 0, m.start()) + 1
        if key in entries:
            dups.append((key, line))
        else:
            entries[key] = {"type": etype, "line": line, "fields": fields}
    return entries, dups


def check(entries, dups):
    errors, warnings = [], []
    for key, line in dups:
        errors.append((line, "duplicate-key", "Duplicate BibTeX key %r." % key))
    for key, e in entries.items():
        for req in REQUIRED.get(e["type"], ["title"]):
            if not any(e["fields"].get(r.strip()) for r in req.split("|")):
                errors.append((e["line"], "missing-field", "%s (%s): missing required field %r." % (key, e["type"], req)))
        for f in ("author", "title", "year", "journal", "publisher"):
            v = e["fields"].get(f)
            if v and SUSPECT.match(v):
                errors.append((e["line"], "suspect-value", "%s: field %s has placeholder value %r (never invent metadata)." % (key, f, v)))
        y = e["fields"].get("year")
        if y and not re.fullmatch(r"(19|20)\d\d[a-z]?", y.strip()):
            warnings.append((e["line"], "odd-year", "%s: unusual year %r." % (key, y)))
        d = e["fields"].get("doi")
        if d and not re.match(r"^10\.\d{4,9}/\S+$", d.strip()):
            warnings.append((e["line"], "bad-doi", "%s: DOI %r does not look valid." % (key, d)))
        if not e["fields"].get("doi") and not e["fields"].get("url") and e["type"] in ("article", "inproceedings"):
            warnings.append((e["line"], "no-locator", "%s: no DOI or URL (verify manually)." % key))
    return errors, warnings


def cited_keys(text):
    keys = set()
    for g in re.finditer(r"\[([^\]\n]*@[^\]\n]*)\]", C.strip_code(text)):
        keys.update(re.findall(r"(?:^|[;\s\-])@([A-Za-z0-9_][\w:.\-]*\w)", g.group(1)))
    keys.update(k.strip() for grp in re.findall(r"\\cite[a-z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}", text) for k in grp.split(","))
    return keys


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bib"); ap.add_argument("--cited-in", nargs="*", default=[])
    a = ap.parse_args(argv)
    if not os.path.isfile(a.bib):
        print("ERROR: not found: %s" % a.bib, file=sys.stderr)
        return 2
    entries, dups = parse_bib(C.read_text(a.bib))
    errors, warnings = check(entries, dups)
    cited = set()
    for f in a.cited_in:
        cited |= cited_keys(C.read_text(f))
    for k in sorted(cited - set(entries)):
        errors.append((0, "undefined-citation", "Cited key %r is not in %s." % (k, a.bib)))
    for k in sorted(set(entries) - cited) if a.cited_in else []:
        warnings.append((entries[k]["line"], "unused-entry", "Entry %r is never cited." % k))
    print("%d entries, %d errors, %d warnings" % (len(entries), len(errors), len(warnings)))
    for ln, code, msg in errors:
        print("ERROR line %s [%s] %s" % (ln, code, msg))
    for ln, code, msg in warnings:
        print("WARN  line %s [%s] %s" % (ln, code, msg))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
