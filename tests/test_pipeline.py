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
