#!/usr/bin/env python3
"""Turn a CSV subset into a captioned pandoc pipe table with a provenance comment (never edits values).

Usage: csv_table.py --csv FILE [--columns a,b,c] [--rows 1-5] --caption TEXT --label tbl-x [--max-cell 60]
Rows are 1-based data rows (header excluded). Prints Markdown to stdout.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402


def build(path, columns, rows, caption, label, max_cell=60):
    with open(path, newline="", encoding="utf-8-sig") as f:
        data = list(csv.DictReader(f))
    if not data:
        raise ValueError("CSV has no data rows")
    cols = columns or list(data[0].keys())
    for c in cols:
        if c not in data[0]:
            raise ValueError("column %r not in CSV (columns: %s)" % (c, ", ".join(data[0].keys())))
    if rows:
        a, _, b = rows.partition("-")
        data = data[int(a) - 1:int(b or a)]
    cell = lambda v: (v if len(v) <= max_cell else v[:max_cell - 1] + "…").replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(cell(r[c]) for c in cols) + " |" for r in data]
    lines += ["", "Table: %s {#%s}" % (caption, label), "",
              "<!-- source: %s columns=%s rows=%s sha256=%s -->" % (path, ",".join(cols), rows or "all", C.sha256_file(path)[:16])]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True); ap.add_argument("--columns"); ap.add_argument("--rows")
    ap.add_argument("--caption", required=True); ap.add_argument("--label", required=True); ap.add_argument("--max-cell", type=int, default=60)
    a = ap.parse_args(argv)
    try:
        print(build(a.csv, a.columns.split(",") if a.columns else None, a.rows, a.caption, a.label, a.max_cell))
    except (OSError, ValueError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
