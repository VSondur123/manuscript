"""Integration tests: approval -> LaTeX -> compile -> PDF inspection. Skipped when tools are missing."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers as H
import ms_common as C
import ms_state as S

SCRIPTS = os.path.join(H.ROOT, "scripts")
HAVE = {t: bool(shutil.which(t)) for t in ("pandoc", "tectonic", "pdftotext", "pdftoppm")}


def ms(*args, cwd):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, args[0])] + list(args[1:]), cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


@unittest.skipUnless(HAVE["pandoc"], "pandoc not installed")
class Pipeline(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ms_pipe_")
        ms("ms_state.py", "init", "demo", "--doctype", "research-report", cwd=self.root)
        self.d = os.path.join(self.root, "manuscript", "demo")
        H.install_fixture(self.d, "demo")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def advance(self, stages):
        for s in stages:
            rc, out = ms("ms_state.py", "stage", s, cwd=self.root)
            self.assertEqual(rc, 0, out)

    def approve(self):
        self.advance(["DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL"])
        self.assertEqual(ms("ms_state.py", "approve-plan", "--phrase", "APPROVE PLAN", cwd=self.root)[0], 0)
        self.advance(["EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"])
        self.assertEqual(ms("validate_markdown.py", cwd=self.root)[0], 0)
        rc, out = ms("ms_state.py", "approve-markdown", "--phrase", "APPROVE MARKDOWN", cwd=self.root)
        self.assertEqual(rc, 0, out)

    def test_latex_refused_before_approval(self):
        rc, out = ms("md_to_latex.py", cwd=self.root)
        self.assertEqual(rc, 2)
        self.assertIn("not currently approved", out)

    def test_latex_refused_after_edit(self):
        self.approve()
        with open(os.path.join(self.d, "demo-report.md"), "a") as f:
            f.write("\nNew claim.\n")
        rc, out = ms("md_to_latex.py", cwd=self.root)
        self.assertEqual(rc, 2)

    def test_latex_uses_approved_snapshot_not_draft(self):
        self.approve()
        draft = os.path.join(self.d, "demo-report.md")
        with open(draft, "a") as f:
            f.write("\nUNAPPROVED-SENTENCE\n")
        # restore draft to the approved bytes -> approval is current again; conversion proceeds from snapshot
        snap = os.path.join(self.d, S.load(self.root, "demo")["markdown_approval"]["snapshot"])
        shutil.copy(snap, draft)
        os.chmod(draft, 0o644)
        self.assertEqual(ms("md_to_latex.py", cwd=self.root)[0], 0)
        tex = C.read_text(os.path.join(self.d, ".ms", "latex", "demo.tex"))
        self.assertNotIn("UNAPPROVED-SENTENCE", tex)
        self.assertIn("\\citep{smith2020}", tex)
        self.assertIn("Figure~\\ref{fig-arch}", tex)

    @unittest.skipUnless(HAVE["tectonic"] and HAVE["pdftotext"] and HAVE["pdftoppm"], "tectonic/poppler not installed")
    def test_full_pipeline_pdf(self):
        self.approve()
        self.assertEqual(ms("md_to_latex.py", cwd=self.root)[0], 0)
        tex = os.path.join(self.d, ".ms", "latex", "demo.tex")
        self.assertEqual(ms("validate_latex.py", tex, cwd=self.root)[0], 0)
        rc, out = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex], capture_output=True, text=True).returncode, ""
        self.assertEqual(rc, 0)
        pdf = os.path.join(self.d, ".ms", "latex", "demo.pdf")
        rc, out = ms("inspect_pdf.py", pdf, "--render-dir", os.path.join(self.d, ".ms", "validation", "pages"), cwd=self.root)
        self.assertEqual(rc, 0, out)
        self.assertIn("1 page", out)
        self.advance(["LATEX_VALIDATION", "PDF_GENERATION", "PDF_QA"])
        self.assertEqual(ms("ms_state.py", "publish", cwd=self.root)[0], 0)
        self.assertEqual(sorted(f for f in os.listdir(self.d) if not f.startswith(".")),
                         ["demo-report.md", "demo.pdf", "demo.tex", "plan.md"])

    def test_reference_list_in_report_but_not_duplicated_in_latex(self):
        rc, out = ms("render_references.py", cwd=self.root)
        self.assertEqual(rc, 0, out)
        report = C.read_text(os.path.join(self.d, "demo-report.md"))
        self.assertIn("<!-- references:start -->", report)
        self.assertIn("key: smith2020", report)
        self.assertEqual(ms("render_references.py", cwd=self.root)[0], 0)  # idempotent
        self.assertEqual(C.read_text(os.path.join(self.d, "demo-report.md")), report)
        self.assertEqual(ms("validate_markdown.py", cwd=self.root)[0], 0)
        self.approve()
        self.assertEqual(ms("md_to_latex.py", cwd=self.root)[0], 0)
        self.assertNotIn("key: smith2020", C.read_text(os.path.join(self.d, ".ms", "latex", "demo.tex")))

    def test_latex_validator_catches_problems(self):  # fixtures 13/14 at LaTeX level
        bad = os.path.join(self.root, "bad.tex")
        with open(bad, "w") as f:
            f.write("\\documentclass{article}\\begin{document}\\citep{nokey} see \\ref{fig:none}"
                    "\\includegraphics{missing.png}\\bibliography{nofile}\\end{document}")
        rc, out = ms("validate_latex.py", bad, cwd=self.root)
        self.assertEqual(rc, 1)
        for needle in ("undefined label", "missing figure", "bibliography file not found"):
            self.assertIn(needle, out)

    @unittest.skipUnless(HAVE["tectonic"], "tectonic not installed")
    def test_compile_error_reported(self):  # fixture 12
        d = os.path.join(self.root, "x", "latex")
        os.makedirs(d)
        tex = os.path.join(d, "bad.tex")
        with open(tex, "w") as f:
            f.write("\\documentclass{article}\\begin{document}\\undefinedmacro\\end{document}")
        r = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("COMPILE FAILED", r.stdout)


GOLDEN = os.path.join(H.FIXTURES, "golden")
STYLE_EXPECT = {  # style -> (in-text substring, reference-list substring, substring that must NOT appear)
    "apa7": ("(Smith & Doe, 2020)", "Smith, J., & Doe, J. (2020). A study of fixtures.", "[1]"),
    "harvard": ("(Smith and Doe, 2020)", "Smith, J. and Doe, J. (2020)", "[1]"),
    "mla9": ("(Smith and Doe)", "Smith, Jane, and John Doe. “A Study of Fixtures.”", "[1]"),
    "chicago-author-date": ("(Smith and Doe 2020)", "Smith, Jane, and John Doe. 2020. “A Study of Fixtures.”", "[1]"),
    "chicago-notes": ("Jane Smith and John Doe, “A Study of Fixtures,”", "Smith, Jane, and John Doe. “A Study of Fixtures.”", "(Smith"),
    "vancouver": ("Prior work [1] motivates", "1. Smith J, Doe J. A study of fixtures.", "(Smith"),
    "ieee": ("Prior work [1] motivates", "[1] J. Smith and J. Doe", "(Smith"),
}
CSL_STYLES = ("apa7", "harvard", "mla9", "chicago-author-date", "chicago-notes", "vancouver")


def norm(text):
    import re
    return re.sub(r"\s+", " ", text)


@unittest.skipUnless(HAVE["pandoc"], "pandoc not installed")
class DefaultPathRegression(unittest.TestCase):
    """No citation_style/layout set: BibTeX/natbib path must reproduce the pre-CSL .tex byte for byte."""

    def setUp(self):
        gv = os.path.join(GOLDEN, "PANDOC_VERSION")
        have = subprocess.run(["pandoc", "--version"], capture_output=True, text=True).stdout.splitlines()[0].strip()
        if C.read_text(gv).strip() != have:
            self.skipTest("golden .tex recorded with %s, installed %s" % (C.read_text(gv).strip(), have))

    def test_byte_identical_for_every_doctype(self):
        for dt in ("research-report", "technical-report", "thesis", "ieee-report"):
            with self.subTest(doctype=dt):
                root, d = H.approved_project("", dt)
                self.addCleanup(shutil.rmtree, root, True)
                self.assertEqual(ms("md_to_latex.py", cwd=root)[0], 0)
                got = C.read_text(os.path.join(d, ".ms", "latex", "demo.tex"))
                self.assertEqual(got, C.read_text(os.path.join(GOLDEN, "%s.tex" % dt)))
                self.assertIn("\\bibliography{references}", got)
                self.assertNotIn("CSLReferences", got)
                self.assertEqual(ms("md_to_latex.py", "--preview", cwd=root)[0], 0)
                prev = C.read_text(os.path.join(d, ".ms", "latex", "demo-preview.tex")).split("\n", 1)[1]
                self.assertEqual(prev, C.read_text(os.path.join(GOLDEN, "%s-preview.tex" % dt)))

    def test_explicit_default_styles_match_doctype_defaults(self):
        for dt, style in (("research-report", "numeric"), ("technical-report", "numeric"), ("thesis", "author-year")):
            with self.subTest(doctype=dt, style=style):
                root, d = H.approved_project("citation_style: %s" % style, dt)
                self.addCleanup(shutil.rmtree, root, True)
                self.assertEqual(ms("md_to_latex.py", cwd=root)[0], 0)
                self.assertEqual(C.read_text(os.path.join(d, ".ms", "latex", "demo.tex")), C.read_text(os.path.join(GOLDEN, "%s.tex" % dt)))


@unittest.skipUnless(HAVE["pandoc"] and HAVE["tectonic"] and HAVE["pdftotext"], "pandoc/tectonic/poppler missing")
class CitationStyles(unittest.TestCase):
    def build(self, style):
        root, d = H.approved_project("citation_style: %s" % style)
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = ms("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        tex = os.path.join(d, ".ms", "latex", "demo.tex")
        self.assertEqual(ms("validate_latex.py", tex, cwd=root)[0], 0)
        r = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex, "tectonic"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        return C.read_text(tex), norm(subprocess.run(["pdftotext", tex[:-4] + ".pdf", "-"], capture_output=True, text=True).stdout)

    def test_each_style_compiles_with_correct_in_text_and_reference_list(self):
        for style, (intext, reflist, absent) in STYLE_EXPECT.items():
            with self.subTest(style=style):
                tex, text = self.build(style)
                self.assertIn(intext, text)
                self.assertIn(reflist, text)
                self.assertNotIn(absent, text)
                self.assertEqual(text.count("References"), 1)  # heading once, list once
                if style in CSL_STYLES:
                    self.assertEqual(tex.count("\\begin{CSLReferences}"), 1)
                    self.assertNotIn("\\bibliography{", tex)
                else:
                    self.assertIn("\\bibliography{references}", tex)

    def test_apa_narrative_citation_and_unnumbered_references(self):
        tex, text = self.build("apa7")
        self.assertIn("Lee (2018)", text)
        self.assertNotRegex(text, r"\d+ References")

    def test_citeproc_validator_catches_missing_key(self):
        root, d = H.approved_project("citation_style: apa7")
        self.addCleanup(shutil.rmtree, root, True)
        ms("md_to_latex.py", cwd=root)
        tex = os.path.join(d, ".ms", "latex", "demo.tex")
        with open(os.path.join(d, ".ms", "latex", "references.bib"), "w") as f:
            f.write("@book{lee2018, author={Lee, A}, title={T}, year={2018}}\n")
        rc, out = ms("validate_latex.py", tex, cwd=root)
        self.assertEqual(rc, 1)
        self.assertIn("citation key not in bibliography: smith2020", out)


@unittest.skipUnless(HAVE["pdftotext"] and HAVE["tectonic"], "tools missing")
class PdfInspection(unittest.TestCase):
    def test_detects_unresolved_and_blank(self):
        d = tempfile.mkdtemp(prefix="ms_pdf_")
        tex = os.path.join(d, "t.tex")
        with open(tex, "w") as f:
            f.write("\\documentclass{article}\\begin{document}See Figure \\ref{nolabel}.\\newpage\\mbox{}\\newpage Last.\\end{document}")
        subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex], capture_output=True)
        rc, out = ms("inspect_pdf.py", os.path.join(d, "t.pdf"), cwd=d)
        self.assertEqual(rc, 1, out)
        self.assertIn("unresolved reference", out)
        self.assertIn("blank", out)
        shutil.rmtree(d, ignore_errors=True)


class Discovery(unittest.TestCase):
    def test_discovers_without_executing(self):  # fixtures 1-3
        from discover import discover
        d = tempfile.mkdtemp(prefix="ms_disc_")
        os.makedirs(os.path.join(d, "src"))
        with open(os.path.join(d, "assignment-guidelines.md"), "w") as f:
            f.write("# Assignment\nReport must be at most 3000 words.\n")
        shutil.copy(os.path.join(d, "assignment-guidelines.md"), os.path.join(d, "copy.md"))
        with open(os.path.join(d, "notes.md"), "w") as f:
            f.write("# Notes\n![fig](missing.png)\n")
        marker = os.path.join(d, "EXECUTED")
        with open(os.path.join(d, "src", "evil.py"), "w") as f:
            f.write("open(%r,'w').write('x')\n" % marker)
        res = discover(d)
        self.assertFalse(os.path.exists(marker))
        self.assertIn("assignment-guidelines.md", res["requirements_candidates"])
        self.assertTrue(any(len(g) == 2 for g in res["exact_duplicates"]))
        self.assertEqual(res["missing_referenced_files"][0]["missing"], "missing.png")
        self.assertEqual(res["counts"]["code"], 1)
        shutil.rmtree(d, ignore_errors=True)

    def test_skips_manuscript_workspace_and_symlinks(self):
        from discover import discover
        d = tempfile.mkdtemp(prefix="ms_disc_")
        os.makedirs(os.path.join(d, "manuscript", "x"))
        open(os.path.join(d, "manuscript", "x", "x-report.md"), "w").close()
        os.symlink("/etc", os.path.join(d, "link"))
        res = discover(d)
        self.assertEqual(res["files"], [])
        self.assertIn("link", res["skipped"])
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
