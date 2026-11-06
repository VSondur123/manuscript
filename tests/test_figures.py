import json
import os
import shutil
import tempfile
import unittest

import helpers as H
import build_figures as BF
import csv_table
import ms_state as S
import validate_markdown as VM

HAVE_ENGINE = any(shutil.which(e) for e in ("tectonic", "xelatex", "pdflatex"))


class SpecValidation(unittest.TestCase):
    def test_unknown_edge_node(self):
        with self.assertRaises(BF.SpecError):
            BF.blocks_tikz({"type": "blocks", "lanes": [{"nodes": [{"id": "a", "text": "A"}]}], "edges": [["a", "zz"]]}, 8.8)

    def test_duplicate_node_and_bad_style(self):
        with self.assertRaises(BF.SpecError):
            BF.blocks_tikz({"lanes": [{"nodes": [{"id": "a", "text": "A"}, {"id": "a", "text": "B"}]}]}, 8.8)
        with self.assertRaises(BF.SpecError):
            BF.blocks_tikz({"lanes": [{"nodes": [{"id": "a", "text": "A", "style": "wild"}]}]}, 8.8)

    def test_latex_escaping(self):
        self.assertEqual(BF.esc("50% & a_b #1"), r"50\% \& a\_b \#1")

    def test_chart_csv_columns_and_numeric(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "x.csv"), "w") as f:
            f.write("k,v\na,1\nb,oops\n")
        with self.assertRaises(BF.SpecError):  # missing column
            BF.load_chart_data({"source": {"csv": "x.csv", "x": "k", "series": ["nope"]}}, d)
        with self.assertRaises(BF.SpecError):  # non-numeric: never coerce/invent
            BF.load_chart_data({"source": {"csv": "x.csv", "x": "k", "series": ["v"]}}, d)
        with self.assertRaises(BF.SpecError):
            BF.load_chart_data({"source": {"csv": "x.csv", "x": "k", "series": ["v"]}, "data": {}}, d)
        xs, series, inputs = BF.load_chart_data({"source": {"csv": "x.csv", "x": "k", "series": ["v"], "rows": "1"}}, d)
        self.assertEqual((xs, series[0]["values"]), (["a"], [1.0]))

    @unittest.skipUnless(HAVE_ENGINE, "no LaTeX engine")
    def test_render_blocks_and_chart(self):
        d = tempfile.mkdtemp()
        spec = {"type": "blocks", "lanes": [{"label": "L", "nodes": [{"id": "a", "text": "A"}, {"id": "b", "text": "B", "style": "gate"}]}],
                "edges": [["a", "b"]]}
        BF.render(spec, "blk", d, d)
        self.assertTrue(os.path.getsize(os.path.join(d, "blk.pdf")) > 500)
        BF.render({"type": "chart", "kind": "line", "data": {"x": ["1", "2"], "series": [{"name": "s", "values": [1, 2]}]}}, "ch", d, d)
        self.assertTrue(os.path.isfile(os.path.join(d, "ch.pdf")))


class CsvTable(unittest.TestCase):
    def test_table_provenance_and_values_untouched(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "t.csv")
        with open(p, "w") as f:
            f.write("a,b\n1,x|y\n2,z\n3,w\n")
        md = csv_table.build(p, ["a", "b"], "1-2", "Cap", "tbl-c")
        self.assertIn("| 1 | x\\|y |", md)
        self.assertNotIn("| 3 |", md)
        self.assertIn("Table: Cap {#tbl-c}", md)
        self.assertIn("<!-- source:", md)
        with self.assertRaises(ValueError):
            csv_table.build(p, ["zzz"], None, "c", "tbl-c")


class FigureLocking(unittest.TestCase):
    """D-011: approval covers figures, their specs and data."""
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ms_fig_")
        S.init_project(self.root, "doc", "research-report")
        self.d = S.pdir(self.root, "doc")
        H.install_fixture(self.d, "doc")
        os.makedirs(os.path.join(self.d, ".ms", "figures-src"))
        with open(os.path.join(self.d, ".ms", "figures-src", "arch.json"), "w") as f:
            json.dump({"type": "blocks"}, f)
        with open(os.path.join(self.d, "data.csv"), "w") as f:
            f.write("a\n1\n")
        sh = S.sha256_file
        with open(os.path.join(self.d, ".ms", "figures", "manifest.json"), "w") as f:
            json.dump({"arch": {"spec": ".ms/figures-src/arch.json", "spec_sha": sh(os.path.join(self.d, ".ms", "figures-src", "arch.json")),
                                "inputs": [{"path": "data.csv", "sha": sh(os.path.join(self.d, "data.csv"))}],
                                "outputs": [".ms/figures/arch.png"]}}, f)
        for s_ in ("DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL"):
            self.go(s_)
        st = S.load(self.root, "doc"); S.approve(self.root, "doc", st, "plan", "APPROVE PLAN"); S.save(self.root, "doc", st)
        for s_ in ("EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"):
            self.go(s_)
        self.assertEqual(VM.main(["--project", "doc", "--root", self.root]), 0)
        st = S.load(self.root, "doc"); S.approve(self.root, "doc", st, "markdown", "APPROVE MARKDOWN"); S.save(self.root, "doc", st)

    def go(self, stage):
        st = S.load(self.root, "doc"); S.set_stage(self.root, "doc", st, stage); S.save(self.root, "doc", st)

    def test_dependencies_recorded(self):
        figs = S.load(self.root, "doc")["markdown_approval"]["figures"]
        self.assertEqual(set(figs), {".ms/figures/arch.png", ".ms/figures-src/arch.json", "data.csv"})
        self.assertEqual(S.markdown_approval_status(self.root, "doc", S.load(self.root, "doc")), "current")

    def test_changing_image_spec_or_data_invalidates(self):
        for rel, extra in ((".ms/figures/arch.png", "x"), (".ms/figures-src/arch.json", " "), ("data.csv", "2\n")):
            with self.subTest(rel=rel):
                with open(os.path.join(self.d, rel), "rb") as f:
                    orig = f.read()
                with open(os.path.join(self.d, rel), "ab") as f:
                    f.write(extra.encode())
                st = S.load(self.root, "doc")
                self.assertEqual(S.markdown_approval_status(self.root, "doc", st), "stale")
                self.assertTrue(any(c["kind"] == "figure_changed" for c in S.verify(self.root, "doc")))
                with open(os.path.join(self.d, rel), "wb") as f:
                    f.write(orig)
                self.assertEqual(S.markdown_approval_status(self.root, "doc", S.load(self.root, "doc")), "current")

    def test_out_of_date_figure_warns(self):
        with open(os.path.join(self.d, ".ms", "figures-src", "arch.json"), "a") as f:
            f.write(" ")
        res = VM.validate(os.path.join(self.d, "doc-report.md"), os.path.join(self.d, ".ms", "references.bib"), None, None, None, self.d)
        self.assertIn("figure-out-of-date", [w["code"] for w in res["warnings"]])


if __name__ == "__main__":
    unittest.main()
