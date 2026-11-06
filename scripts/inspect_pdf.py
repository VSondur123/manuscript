#!/usr/bin/env python3
"""Inspect a compiled PDF using poppler tools (no Python dependencies).

Usage: inspect_pdf.py file.pdf [--render-dir DIR] [--dpi 60] [--max-pages N] [--min-margin-mm 15] [--json]
Checks: page count/size, fonts (incl. non-embedded), blank pages, '??'/'(author?)' unresolved refs,
text per page, ink touching page edges (clipping), margins (estimated from rendered pixels),
very short last page, headings stranded at page bottom (heuristic).
Renders PNGs to --render-dir so a human/Claude can LOOK at each page (not just trust the log).
Exit 0 = no errors, 1 = errors, 2 = usage / tools missing. Heuristics are advisory, see Limitations in README.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402


def run(cmd, binary=False):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("%s failed: %s" % (cmd[0], r.stderr.decode("utf-8", "replace")[:200]))
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def read_ppm(data):
    """Parse binary P6/P5 PPM/PGM -> (w, h, channels, pixels bytes)."""
    m = re.match(rb"(P[56])\s+(\d+)\s+(\d+)\s+(\d+)\s", data)
    if not m:
        raise ValueError("not a PPM")
    ch = 3 if m.group(1) == b"P6" else 1
    return int(m.group(2)), int(m.group(3)), ch, data[m.end():]


def ink_bbox(w, h, ch, px, thresh=235):
    """Bounding box (x0,y0,x1,y1) of non-white pixels; None if blank."""
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = px[y * w * ch:(y + 1) * w * ch]
        if ch == 3:
            vals = [min(row[i], row[i + 1], row[i + 2]) for i in range(0, len(row), 3)]
        else:
            vals = list(row)
        xs = [x for x, v in enumerate(vals) if v < thresh]
        if xs:
            y0 = min(y0, y); y1 = max(y1, y)
            x0 = min(x0, xs[0]); x1 = max(x1, xs[-1])
    return None if x1 < 0 else (x0, y0, x1, y1)


def inspect(pdf, render_dir=None, dpi=60, min_margin_mm=15, max_pages=None):
    res = {"file": pdf, "errors": [], "warnings": [], "pages": [], "info": {}}
    for tool in ("pdfinfo", "pdftotext", "pdftoppm", "pdffonts"):
        if not C.which(tool):
            raise RuntimeError("%s not found (install poppler)" % tool)
    info = run(["pdfinfo", pdf])
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
    size = re.search(r"^Page size:\s+([\d.]+) x ([\d.]+) pts(?: \((\w+)\))?", info, re.M)
    res["info"] = {"pages": pages, "page_size_pts": [float(size.group(1)), float(size.group(2))] if size else None,
                   "paper": size.group(3) if size else None}
    if max_pages and pages > max_pages:
        res["errors"].append("page count %d exceeds limit %d" % (pages, max_pages))
    fonts = run(["pdffonts", pdf]).splitlines()[2:]
    flist, notemb = [], []
    for ln in fonts:
        parts = ln.split()
        if len(parts) >= 5:
            flist.append(parts[0].split("+")[-1])
            m = re.search(r"\s(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", ln)
            if m and m.group(1) == "no":
                notemb.append(parts[0])
    res["info"]["fonts"] = sorted(set(flist))
    if notemb:
        res["warnings"].append("fonts not embedded: %s" % ", ".join(sorted(set(notemb))))
    full = run(["pdftotext", "-layout", pdf, "-"])
    texts = full.split("\f")[:pages]
    for pat, label in ((r"\?\?", "unresolved reference '??'"), (r"\(author\?\)|\(\?\)", "unresolved citation '(author?)'"),
                       (r"\[\?\]", "unresolved citation '[?]'")):
        if re.search(pat, full):
            res["errors"].append("%s found in PDF text" % label)
    if render_dir:
        os.makedirs(render_dir, exist_ok=True)
        stem = os.path.join(render_dir, "page")
        run(["pdftoppm", "-png", "-r", str(max(dpi, 80)), pdf, stem])
    # pixel probe: render grayscale PGMs into a temp dir and measure the ink bounding box
    import tempfile
    mm_per_px = 25.4 / dpi
    with tempfile.TemporaryDirectory() as td:
        run(["pdftoppm", "-gray", "-r", str(dpi), pdf, os.path.join(td, "p")])
        files = sorted(f for f in os.listdir(td) if f.endswith(".pgm"))
        for i, fn in enumerate(files):
            with open(os.path.join(td, fn), "rb") as fh:
                w, h, ch, px = read_ppm(fh.read())
            bb = ink_bbox(w, h, ch, px)
            txt = texts[i] if i < len(texts) else ""
            pg = {"page": i + 1, "words": len(txt.split()), "blank": False}
            toks = txt.split()
            if len(toks) <= 1 and (not toks or re.fullmatch(r"[\divxlcIVXLC]+", toks[0])):
                pg["blank"] = True
                res["errors"].append("page %d is blank (no content%s)" % (i + 1, " apart from the page number" if toks else ""))
            if bb is None:
                pass
            else:
                l, t, r_, b = bb[0] * mm_per_px, bb[1] * mm_per_px, (w - 1 - bb[2]) * mm_per_px, (h - 1 - bb[3]) * mm_per_px
                pg["margins_mm"] = {"left": round(l, 1), "top": round(t, 1), "right": round(r_, 1), "bottom": round(b, 1)}
                if min(l, r_) < 1.5 or bb[1] == 0 or bb[3] == h - 1:
                    res["errors"].append("page %d: content touches/clips the page edge (L%.1f R%.1f mm)" % (i + 1, l, r_))
                elif l < min_margin_mm * 0.6 or r_ < min_margin_mm * 0.6:
                    res["warnings"].append("page %d: narrow side margin (L%.1f R%.1f mm) - possible overflow" % (i + 1, l, r_))
            lines = [x for x in txt.splitlines() if x.strip()]
            if lines and re.match(r"^\s*(\d+(\.\d+)*\s+)?[A-Z][^.]{2,60}$", lines[-2] if len(lines) > 1 and re.fullmatch(r"\s*\d+\s*", lines[-1]) else lines[-1]) and i < pages - 1:
                cand = lines[-2] if len(lines) > 1 and re.fullmatch(r"\s*\d+\s*", lines[-1]) else lines[-1]
                if re.match(r"^\s*\d+(\.\d+)*\s+\S", cand):
                    res["warnings"].append("page %d may end with an orphaned heading: %r" % (i + 1, cand.strip()))
            res["pages"].append(pg)
    if pages > 1 and res["pages"] and res["pages"][-1]["words"] < 15 and not res["pages"][-1]["blank"]:
        res["warnings"].append("last page has very little text (%d words)" % res["pages"][-1]["words"])
    if render_dir:
        res["info"]["rendered_pngs"] = sorted(os.path.join(render_dir, f) for f in os.listdir(render_dir) if f.startswith("page") and f.endswith(".png"))
    res["info"]["not_checked"] = ["table overflow beyond margins is only caught via ink/edge heuristic",
                                  "caption placement and figure quality require visual review of rendered PNGs",
                                  "header/footer consistency not machine-checked"]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("--render-dir"); ap.add_argument("--dpi", type=int, default=60)
    ap.add_argument("--max-pages", type=int); ap.add_argument("--min-margin-mm", type=float, default=15)
    ap.add_argument("--json", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.pdf):
        print("ERROR: not found: %s" % a.pdf, file=sys.stderr)
        return 2
    try:
        res = inspect(a.pdf, a.render_dir, a.dpi, a.min_margin_mm, a.max_pages)
    except (RuntimeError, ValueError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    if a.out:
        C.write_json(a.out, res)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        i = res["info"]
        print("%s: %d page(s), %s, fonts: %s" % (os.path.basename(a.pdf), i["pages"], i["paper"] or i["page_size_pts"], ", ".join(i["fonts"]) or "none"))
        for p in res["pages"]:
            print("  p%d: %d words, margins(mm)=%s%s" % (p["page"], p["words"], p.get("margins_mm"), " BLANK" if p["blank"] else ""))
        for e in res["errors"]:
            print("ERROR " + e)
        for w in res["warnings"]:
            print("WARN  " + w)
        if i.get("rendered_pngs"):
            print("Rendered pages (look at them): " + ", ".join(i["rendered_pngs"]))
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
