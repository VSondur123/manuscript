#!/usr/bin/env python3
"""Render figure specs (figures-src/*.json) to vector PDF + PNG using TikZ/pgfplots (stdlib only).

Usage:
  build_figures.py [--project ID] [--root DIR] [--only NAME] [--check]
  build_figures.py --spec file.json --outdir DIR [--base-dir DIR]
Outputs figures/<name>.pdf, figures/<name>.png and figures/manifest.json (spec + input hashes, provenance).
Never invents data: chart values come only from a CSV or inline data in the spec.
Spec types: "blocks" (lanes of boxes with arrows) and "chart" (kind: bar | line). See references/figures.md.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402
import ms_state as S  # noqa: E402


class SpecError(Exception):
    pass


def esc(t):
    out = []
    for ch in str(t):
        out.append({"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}.get(ch, ch))
    return "".join(out).replace("\n", r"\\ ")


STYLES = {
    "default": "draw, rounded corners=2pt, fill=white",
    "gate": "draw, thick, rounded corners=2pt, fill=yellow!25",
    "artifact": "draw, dashed, rounded corners=2pt, fill=gray!10",
    "start": "draw, thick, rounded corners=6pt, fill=blue!10",
    "end": "draw, thick, rounded corners=6pt, fill=green!15",
}


def blocks_tikz(spec, width_cm):
    lanes = spec.get("lanes")
    if not lanes or not isinstance(lanes, list):
        raise SpecError("blocks spec needs a non-empty 'lanes' list")
    orient = spec.get("orientation", "vertical")
    if orient not in ("vertical", "horizontal"):
        raise SpecError("orientation must be 'vertical' or 'horizontal'")
    names, order = {}, []
    for li, lane in enumerate(lanes):
        if "nodes" not in lane or not lane["nodes"]:
            raise SpecError("lane %r has no nodes" % lane.get("label", li))
        for ni, n in enumerate(lane["nodes"]):
            if "id" not in n or "text" not in n:
                raise SpecError("every node needs 'id' and 'text'")
            if n["id"] in names:
                raise SpecError("duplicate node id %r" % n["id"])
            if n.get("style", "default") not in STYLES:
                raise SpecError("unknown node style %r (valid: %s)" % (n["style"], ", ".join(STYLES)))
            row = int(n.get("row", ni))
            names[n["id"]] = ("n%d_%d" % (li, ni), li, row)
            order.append((n, li, row))
    for e in spec.get("edges", []):
        a, b = (e[0], e[1]) if isinstance(e, list) else (e.get("from"), e.get("to"))
        for x in (a, b):
            if x not in names:
                raise SpecError("edge references unknown node %r" % x)
    nl = len(lanes)
    nrows = max(r for _, _, r in order) + 1
    gap, vgap, node_h = 0.35, 0.45, float(spec.get("node_height_cm", 0.95))
    if orient == "vertical":
        node_w = (width_cm - 0.4 - (nl - 1) * gap) / nl
        pos = lambda li, r: (li * (node_w + gap) + node_w / 2, -r * (node_h + vgap))
    else:
        label_w = 1.6
        node_w = (width_cm - label_w - 0.2 - (nrows - 1) * gap) / nrows
        pos = lambda li, r: (label_w + r * (node_w + gap) + node_w / 2, -li * (node_h + vgap + 0.35))
    out = [r"\begin{tikzpicture}[font=\scriptsize, >=Stealth, node distance=0.3cm, "
           r"blk/.style={align=center, text width=%.2fcm, minimum height=%.2fcm, inner sep=2pt}]" % (node_w - 0.2, node_h)]
    for n, li, r in order:
        x, y = pos(li, r)
        out.append(r"\node[blk, %s] (%s) at (%.3f,%.3f) {%s};" % (STYLES[n.get("style", "default")], names[n["id"]][0], x, y, esc(n["text"])))
    titles, fits = [], []
    for li, lane in enumerate(lanes):
        members = " ".join("(%s)" % names[n["id"]][0] for n in lane["nodes"])
        title = esc(lane.get("label", ""))
        if orient == "vertical":
            top = max(pos(li, r)[1] for n, l, r in order if l == li)
            x = pos(li, 0)[0]
            titles.append(r"\node[font=\footnotesize\bfseries] (t%d) at (%.3f,%.3f) {%s};" % (li, x, top + node_h / 2 + 0.45, title))
            fits.append(r"\node[fit=%s (t%d), fill=gray!8, rounded corners=3pt, inner sep=3pt] {};" % (members, li))
        else:
            y = pos(li, 0)[1]
            titles.append(r"\node[font=\footnotesize\bfseries, align=right, text width=1.4cm] (t%d) at (0.7,%.3f) {%s};" % (li, y, title))
            fits.append(r"\node[fit=%s, fill=gray!8, rounded corners=3pt, inner sep=3pt] {};" % members)
    out.extend(titles)
    out.append(r"\begin{scope}[on background layer]")
    out.extend(fits)
    out.append(r"\end{scope}")
    for e in spec.get("edges", []):
        if isinstance(e, list):
            a, b, lab, sty = e[0], e[1], (e[2] if len(e) > 2 else None), None
        else:
            a, b, lab, sty = e["from"], e["to"], e.get("label"), e.get("style")
        (na, la, ra), (nb, lb, rb) = names[a], names[b]
        if la == lb and ra != rb:
            ap, bp = ("south", "north") if rb > ra else ("north", "south")
            if orient == "horizontal":
                ap, bp = ("east", "west") if rb > ra else ("west", "east")
        elif ra == rb and la != lb:
            ap, bp = ("east", "west") if lb > la else ("west", "east")
            if orient == "horizontal":
                ap, bp = ("south", "north") if lb > la else ("north", "south")
        else:
            ap = bp = None
        src = "(%s.%s)" % (na, ap) if ap else "(%s)" % na
        dst = "(%s.%s)" % (nb, bp) if bp else "(%s)" % nb
        opt = "->" + (", dashed" if sty == "dashed" else "")
        label = r" node[midway, fill=white, inner sep=1pt, font=\tiny] {%s}" % esc(lab) if lab else ""
        out.append(r"\draw[%s] %s -- %s%s;" % (opt, src, dst, label))
    out.append(r"\end{tikzpicture}")
    return "\n".join(out), ["positioning", "fit", "backgrounds", "arrows.meta"], False


def load_chart_data(spec, base_dir):
    inputs = []
    if "source" in spec and "data" in spec:
        raise SpecError("use either 'source' (CSV) or 'data' (inline), not both")
    if "source" in spec:
        src = spec["source"]
        path = os.path.normpath(os.path.join(base_dir, src["csv"]))
        if not os.path.isfile(path):
            raise SpecError("CSV not found: %s" % src["csv"])
        inputs.append(path)
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            raise SpecError("CSV has no data rows: %s" % src["csv"])
        cols = rows[0].keys()
        for c in [src["x"]] + list(src["series"]):
            if c not in cols:
                raise SpecError("column %r not in CSV (columns: %s)" % (c, ", ".join(cols)))
        if "rows" in src:
            a, _, b = str(src["rows"]).partition("-")
            lo, hi = int(a), int(b or a)
            rows = rows[lo - 1:hi]
        xs = [r[src["x"]] for r in rows]
        series = []
        for c in src["series"]:
            try:
                series.append({"name": c, "values": [float(r[c]) for r in rows]})
            except ValueError as e:
                raise SpecError("non-numeric value in column %r: %s" % (c, e))
        return xs, series, inputs
    d = spec.get("data")
    if not d:
        raise SpecError("chart needs 'source' (csv) or 'data'")
    xs = [str(x) for x in d["x"]]
    series = []
    for s in d["series"]:
        if len(s["values"]) != len(xs):
            raise SpecError("series %r has %d values for %d x labels" % (s["name"], len(s["values"]), len(xs)))
        series.append({"name": s["name"], "values": [float(v) for v in s["values"]]})
    return xs, series, inputs


def chart_tikz(spec, width_cm, base_dir):
    kind = spec.get("kind", "bar")
    if kind not in ("bar", "line"):
        raise SpecError("chart kind must be 'bar' or 'line'")
    xs, series, inputs = load_chart_data(spec, base_dir)
    n = len(xs)
    labels = ",".join("{%s}" % esc(x) for x in xs)
    opts = ["width=%.2fcm" % width_cm, "height=%.2fcm" % float(spec.get("height_cm", 5.2)),
            "xtick={%s}" % ",".join(str(i) for i in range(n)), "xticklabels={%s}" % labels,
            "x tick label style={font=\\tiny, rotate=%d, anchor=%s}" % ((30, "east") if n > 4 else (0, "north")),
            "tick label style={font=\\scriptsize}", "label style={font=\\scriptsize}", "ymajorgrids=true",
            "grid style={gray!25}", "enlarge x limits=%s" % ("0.15" if kind == "bar" else "0.1")]
    if spec.get("xlabel"):
        opts.append("xlabel={%s}" % esc(spec["xlabel"]))
    if spec.get("ylabel"):
        opts.append("ylabel={%s}" % esc(spec["ylabel"]))
    if spec.get("ymin") is not None or kind == "bar":
        opts.append("ymin=%s" % spec.get("ymin", 0))
    if kind == "bar":
        opts += ["ybar", "bar width=%.1fpt" % max(3, 22 / max(len(series), 1))]
    if len(series) > 1:
        opts.append("legend style={font=\\tiny, at={(0.5,1.03)}, anchor=south, legend columns=-1}")
    body = [r"\begin{tikzpicture}", r"\begin{axis}[%s]" % ", ".join(opts)]
    marks = ["*", "square*", "triangle*", "diamond*"]
    for i, s in enumerate(series):
        extra = "mark=%s" % marks[i % 4] if kind == "line" else "fill=gray!%d" % (35 + 45 * i // max(len(series), 1))
        pts = " ".join("(%d,%s)" % (j, repr(v)) for j, v in enumerate(s["values"]))
        body.append(r"\addplot[%s] coordinates {%s};" % (extra, pts))
        if len(series) > 1:
            body.append(r"\addlegendentry{%s}" % esc(s["name"]))
    body += [r"\end{axis}", r"\end{tikzpicture}"]
    return "\n".join(body), [], True, inputs


def render(spec, name, outdir, base_dir):
    """Render one spec; returns list of input files read."""
    width = float(spec.get("width_cm", 8.8))
    inputs = []
    if spec.get("type") == "blocks":
        tikz, libs, pgf = blocks_tikz(spec, width)[:3]
    elif spec.get("type") == "chart":
        tikz, libs, pgf, inputs = chart_tikz(spec, width, base_dir)
    else:
        raise SpecError("spec 'type' must be 'blocks' or 'chart'")
    doc = ["\\documentclass[border=3pt]{standalone}", "\\usepackage{tikz}",
           "\\usetikzlibrary{%s}" % ",".join(libs or ["arrows.meta"])]
    if pgf:
        doc += ["\\usepackage{pgfplots}", "\\pgfplotsset{compat=1.16}"]
    doc += ["\\begin{document}", tikz, "\\end{document}"]
    os.makedirs(outdir, exist_ok=True)
    engine = next((e for e in ("tectonic", "xelatex", "pdflatex") if shutil.which(e)), None)
    if not engine:
        raise SpecError("no LaTeX engine found to render figures (tectonic recommended)")
    with tempfile.TemporaryDirectory() as td:
        tex = os.path.join(td, "fig.tex")
        with open(tex, "w", encoding="utf-8") as f:
            f.write("\n".join(doc))
        cmd = [engine, "fig.tex"] if engine == "tectonic" else [engine, "-interaction=nonstopmode", "-halt-on-error", "fig.tex"]
        r = subprocess.run(cmd, cwd=td, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(os.path.join(td, "fig.pdf")):
            raise SpecError("LaTeX failed rendering %s:\n%s" % (name, (r.stdout + r.stderr)[-1500:]))
        shutil.copy2(os.path.join(td, "fig.pdf"), os.path.join(outdir, name + ".pdf"))
        if shutil.which("pdftoppm"):
            subprocess.run(["pdftoppm", "-png", "-r", "170", "-singlefile", os.path.join(outdir, name + ".pdf"),
                            os.path.join(outdir, name)], capture_output=True)
    return inputs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project"); ap.add_argument("--root", default=os.getcwd()); ap.add_argument("--only")
    ap.add_argument("--check", action="store_true", help="only report figures that are missing or out of date")
    ap.add_argument("--spec"); ap.add_argument("--outdir"); ap.add_argument("--base-dir")
    a = ap.parse_args(argv)
    try:
        if a.spec:
            spec = C.read_json(a.spec) if hasattr(C, "read_json") else json.load(open(a.spec))
            name = os.path.splitext(os.path.basename(a.spec))[0]
            render(spec, name, a.outdir or ".", a.base_dir or os.path.dirname(os.path.abspath(a.spec)))
            print("Rendered %s" % name)
            return 0
        root = os.path.abspath(a.root)
        pid = S.resolve(root, a.project)
        d = S.pdir(root, pid)
        src_dir, out_dir = os.path.join(d, S.WORK, "figures-src"), os.path.join(d, S.WORK, "figures")
        specs = sorted(f for f in os.listdir(src_dir) if f.endswith(".json")) if os.path.isdir(src_dir) else []
        mpath = os.path.join(out_dir, "manifest.json")
        manifest = C.read_json(mpath) if os.path.isfile(mpath) else {}
        problems, built = 0, 0
        for fn in specs:
            name = fn[:-5]
            if a.only and a.only != name:
                continue
            spath = os.path.join(src_dir, fn)
            sha = C.sha256_file(spath)
            ent = manifest.get(name)
            stale = (not ent or ent["spec_sha"] != sha or not os.path.isfile(os.path.join(out_dir, name + ".pdf"))
                     or any(not os.path.isfile(os.path.join(d, i["path"])) or C.sha256_file(os.path.join(d, i["path"])) != i["sha"]
                            for i in ent.get("inputs", [])))
            if a.check:
                print("%s: %s" % (name, "OUT OF DATE or missing" if stale else "up to date"))
                problems += stale
                continue
            spec = C.read_json(spath)
            ins = render(spec, name, out_dir, d)
            manifest[name] = {"spec": os.path.relpath(spath, d), "spec_sha": sha,
                              "inputs": [{"path": os.path.relpath(p, d), "sha": C.sha256_file(p)} for p in ins],
                              "outputs": [".ms/figures/%s.pdf" % name, ".ms/figures/%s.png" % name],
                              "built_at": C.now(), "caption": spec.get("caption")}
            built += 1
            print("built .ms/figures/%s.pdf (+png)" % name)
        if not a.check:
            os.makedirs(out_dir, exist_ok=True)
            C.write_json(mpath, manifest)
            print("%d figure(s) built; manifest updated" % built)
        return 1 if problems else 0
    except (SpecError, S.StateError, KeyError, ValueError, OSError) as e:
        print("ERROR: %s" % (e if not isinstance(e, KeyError) else "missing key %s in spec" % e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
