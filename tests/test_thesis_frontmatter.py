"""Opt-in formal thesis front/back matter (doctype thesis-formal): pipeline, escaping, logo locking, validation, default path."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers as H
import layout as L
import ms_common as C
import ms_state as S
import validate_markdown as V

SCRIPTS = os.path.join(H.ROOT, "scripts")
HAVE = {t: bool(shutil.which(t)) for t in ("pandoc", "tectonic", "pdftotext")}
FULL = HAVE["pandoc"] and HAVE["tectonic"] and HAVE["pdftotext"]

CONFIG = """frontmatter:
  institution: Example University & Co_1
  department: Department of Computer Science
  degree: Master of Science
  supervisor:
    - Prof. Ada Supervisor
    - Dr. Grace Cosupervisor
  logo: logo.png
  declaration: true
  copyright: true
  dedication: For my family
  lof: true
  lot: true
  roman_front_matter: true"""

FRONT = """---
title: "A Formal Thesis on 50% Fixtures"
subtitle: Testing the Front Matter
author: Test Author
date: 1 November 2026
abstract: |
  This is the thesis abstract.
keywords: [fixtures, front matter]
acknowledgements: |
  Thanks to the fixture committee.
abbreviations:
  - term: API
    meaning: Application Programming Interface
  - term: R&D
    meaning: Research and Development
---
"""


def ms(*args, cwd):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, args[0])] + list(args[1:]), cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def formal_project(config=CONFIG, appendix=True, logo=True, citation=None):
    """Temp workspace: fixture body with formal front matter, approved through the real state engine (harness phrases)."""
    root = tempfile.mkdtemp(prefix="ms_formal_")
    ms("ms_state.py", "init", "demo", "--doctype", "thesis-formal", cwd=root)
    d = os.path.join(root, "manuscript", "demo")
    H.install_fixture(d, "demo")
    rp = os.path.join(d, "demo-report.md")
    body = C.read_text(rp).split("---\n", 2)[2]
    body = body.replace("# Methodology", "# Literature Review\n\nBackground text.\n\n# Methodology").replace(
        "# Conclusion", "# Discussion\n\nDiscussion text.\n\n# Conclusion")
    if "# References" not in body:
        body = body.rstrip("\n") + "\n\n# References\n"
    if appendix:
        body = body.rstrip("\n") + "\n\n# Supplementary Material {.appendix}\n\nExtra detail [@lee2018].\n\n![Appendix figure](.ms/figures/arch.png){#fig-app}\n\n| K | V |\n|---|---|\n| x | 1 |\n\nTable: Appendix table {#tbl-app}\n\n# More Detail {.appendix}\n\nSecond appendix.\n"
    with open(rp, "w", encoding="utf-8") as f:
        f.write(FRONT + body)
    if logo:
        shutil.copy(os.path.join(d, ".ms", "figures", "arch.png"), os.path.join(d, "logo.png"))
    with open(os.path.join(d, ".ms", "project-config.yaml"), "a", encoding="utf-8") as f:
        f.write("\n" + (config or "") + ("\ncitation_style: %s\n" % citation if citation else "\n"))
    return root, d


def approve(root, d):
    for s in ["DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL"]:
        ms("ms_state.py", "stage", s, cwd=root)
    ms("ms_state.py", "approve-plan", "--phrase", "APPROVE PLAN", cwd=root)
    for s in ["EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"]:
        ms("ms_state.py", "stage", s, cwd=root)
    ms("validate_markdown.py", cwd=root)
    rc, out = ms("ms_state.py", "approve-markdown", "--phrase", "APPROVE MARKDOWN", cwd=root)
    assert rc == 0, out


def pdf_text(root, d, style=None):
    tex = os.path.join(d, ".ms", "latex", "demo.tex")
    r = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex, "tectonic"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    return subprocess.run(["pdftotext", "-layout", tex[:-4] + ".pdf", "-"], capture_output=True, text=True).stdout


@unittest.skipUnless(FULL, "pandoc/tectonic/poppler missing")
class FormalThesisPipeline(unittest.TestCase):
    def build(self, citation=None, **kw):
        root, d = formal_project(citation=citation, **kw)
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(ms("ms_state.py", "lock-logo", cwd=root)[0], 0)
        approve(root, d)
        self.assertEqual(ms("ms_state.py", "check-config", cwd=root)[0], 0)
        rc, out = ms("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertEqual(ms("validate_latex.py", os.path.join(d, ".ms", "latex", "demo.tex"), cwd=root)[0], 0)
        return root, d, pdf_text(root, d)

    def test_full_front_and_back_matter(self):
        root, d, text = self.build()
        tex = C.read_text(os.path.join(d, ".ms", "latex", "demo.tex"))
        first_page = text.split("\f")[0]
        for needle in ("Example University & Co_1", "Department of Computer Science", "A Formal Thesis on 50% Fixtures",
                       "Testing the Front Matter", "Master of Science", "Test Author", "Prof. Ada Supervisor; Dr. Grace Cosupervisor"):
            self.assertIn(needle, first_page)
        for needle in ("Declaration", "I declare that this thesis", "Copyright", "For my family", "Abstract", "This is the thesis abstract.",
                       "Keywords: fixtures, front matter", "Acknowledgements", "Thanks to the fixture committee.", "Contents",
                       "List of Figures", "List of Tables", "List of Abbreviations", "Application Programming Interface",
                       "R&D", "Research and Development", "Appendix A", "Supplementary Material", "Appendix B"):
            self.assertIn(needle, text)
        self.assertIn("\\includegraphics[width=0.5\\linewidth,height=2.5cm,keepaspectratio]{ms-logo.png}", tex)
        self.assertIn("\\pagenumbering{roman}", tex)
        self.assertIn("\\appendix", tex)
        self.assertEqual(tex.count("\\appendix"), 1)
        self.assertGreater(tex.index("\\appendix"), tex.index("\\bibliography{references}"))  # references before appendices
        self.assertLess(text.rindex("A study of fixtures"), text.rindex("Appendix A\n"))
        self.assertEqual(text.count("Appendix figure"), 2)  # list of figures entry + caption
        self.assertNotIn("Bibliography", text)
        # free text was escaped by pandoc, never raw
        self.assertIn("Example University \\& Co\\_1", tex)
        self.assertIn("50\\%", tex)
        self.assertRegex(text, r"\n\s+i{1,3}v?\s*\n")  # roman folio in the front matter
        self.assertIn("Chapter 1", text)

    def test_apa7_and_default_author_year_compile(self):
        for style, expect in (("apa7", "(Smith & Doe, 2020)"), ("author-year", "Smith")):
            with self.subTest(style=style):
                root, d, text = self.build(citation=style)
                self.assertIn(expect, " ".join(text.split()))
                self.assertIn("Appendix A", text)
                self.assertIn("References", text)
                self.assertLess(text.rindex("A study of fixtures"), text.rindex("Appendix A\n"))

    def test_default_citation_is_author_year_bibtex(self):
        root, d, text = self.build()
        tex = C.read_text(os.path.join(d, ".ms", "latex", "demo.tex"))
        self.assertIn("\\bibliography{references}", tex)

    def test_layout_options_work_with_the_template(self):
        root, d = formal_project(config=CONFIG + "\nlayout:\n  paper: letter\n  font_size: 11\n  spacing: single\n  header: running-title\n  page_numbers: bottom-right")
        self.addCleanup(shutil.rmtree, root, True)
        ms("ms_state.py", "lock-logo", cwd=root)
        approve(root, d)
        self.assertEqual(ms("ms_state.py", "check-config", cwd=root)[0], 0)
        self.assertEqual(ms("md_to_latex.py", cwd=root)[0], 0)
        self.assertIn("A Formal Thesis", pdf_text(root, d))

    def test_preview_works(self):
        root, d = formal_project()
        self.addCleanup(shutil.rmtree, root, True)
        ms("ms_state.py", "lock-logo", cwd=root)
        rc, out = ms("md_to_latex.py", "--preview", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertIn("DRAFT PREVIEW", C.read_text(os.path.join(d, ".ms", "latex", "demo-preview.tex")))


@unittest.skipUnless(HAVE["pandoc"], "pandoc not installed")
class FormalThesisSafety(unittest.TestCase):
    def test_config_text_is_literal_not_latex(self):
        evil = r"Evil \input{/etc/passwd} \write18{x} $x$ [@cite] `code` *b*"
        root, d = formal_project(config='frontmatter:\n  institution: "%s"\n  degree: Doc' % evil.replace('"', ""), logo=False)
        self.addCleanup(shutil.rmtree, root, True)
        approve(root, d)
        self.assertEqual(ms("md_to_latex.py", cwd=root)[0], 0)
        tex = C.read_text(os.path.join(d, ".ms", "latex", "demo.tex"))
        self.assertNotIn("\\input{/etc", tex)
        self.assertNotIn("\\write18{", tex)
        self.assertIn("textbackslash", tex)
        self.assertNotIn("\\emph{b}", tex)

    def test_logo_drift_detected_and_blocks_generation(self):
        root, d = formal_project()
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(ms("ms_state.py", "lock-logo", cwd=root)[0], 0)
        st = json.load(open(os.path.join(d, ".ms", "state.json")))
        locked = os.path.join(d, st["logo"]["path"])
        self.assertTrue(locked.startswith(os.path.join(d, ".ms")) and os.path.isfile(locked))
        self.assertEqual(st["logo"]["sha256"], C.sha256_file(locked))
        approve(root, d)
        st = json.load(open(os.path.join(d, ".ms", "state.json")))
        self.assertIn(st["logo"]["path"], st["markdown_approval"]["figures"])  # approval covers the logo like a figure
        self.assertEqual(ms("md_to_latex.py", cwd=root)[0], 0)
        self.assertEqual(ms("ms_state.py", "verify", cwd=root)[0], 0)
        os.chmod(locked, 0o644)
        with open(locked, "ab") as f:
            f.write(b"tamper")
        rc, out = ms("ms_state.py", "verify", cwd=root)
        self.assertEqual(rc, 3)
        self.assertIn("logo_changed", out)
        self.assertIn("figure_changed", out)  # the Markdown approval went stale too
        rc, out = ms("md_to_latex.py", cwd=root)
        self.assertNotEqual(rc, 0)
        self.assertIn("approved", out.lower())
        os.unlink(locked)
        self.assertIn("logo_missing", ms("ms_state.py", "verify", cwd=root)[1])

    def test_unlocked_logo_is_reported(self):
        root, d = formal_project()
        self.addCleanup(shutil.rmtree, root, True)
        p = os.path.join(d, ".ms", "state.json")
        st = json.load(open(p)); st["doctype"] = "thesis"; json.dump(st, open(p, "w"))
        rc, out = ms("ms_state.py", "check-config", cwd=root)  # plain thesis: frontmatter would be ignored, so rejected
        self.assertEqual(rc, 1)
        self.assertIn("thesis-formal", out)
        st["doctype"] = "thesis-formal"; json.dump(st, open(p, "w"))
        rc, out = ms("ms_state.py", "check-config", cwd=root)
        self.assertEqual(rc, 1)
        self.assertIn("lock-logo", out)

    def test_check_config_rejects_bad_keys(self):
        dt = C.load_yaml(os.path.join(H.DOCTYPES, "thesis-formal.yaml"))
        for block, frag in (({"colour": "red"}, "unknown option"), ({"lof": "yes please"}, "true or false"),
                            ({"logo": "../../etc/x.png"}, "plain file path"), ({"logo": "x.exe"}, "plain file path"),
                            ({"supervisor": [["a"]]}, "list of names")):
            errs = L.check_config(dt, {"frontmatter": block})
            self.assertTrue(any(frag in e for e in errs), (block, errs))
        self.assertEqual(L.check_config(dt, {"frontmatter": {"supervisor": ["A", "B"], "lof": True, "logo": "logos/u.png"}}), [])
        self.assertTrue(L.check_config(C.load_yaml(os.path.join(H.DOCTYPES, "thesis.yaml")), {"frontmatter": {"degree": "x"}}))

    def test_validator_warns_not_errors_when_fields_missing(self):
        dt = C.load_yaml(os.path.join(H.DOCTYPES, "thesis-formal.yaml"))
        d = tempfile.mkdtemp(prefix="ms_v_")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "r.md")
        text = "---\ntitle: T\nabstract: A\n---\n\n# Introduction\n\nBody text.\n"
        open(p, "w").write(text)
        res = V.validate(p, doctype=dt, config={})
        warn = [w["message"] for w in res["warnings"] if w["code"] == "frontmatter-missing"]
        for field in ("supervisor", "degree", "department", "institution", "declaration", "keywords", "author"):
            self.assertTrue(any(field in w for w in warn), (field, warn))
        self.assertFalse([e for e in res["errors"] if "frontmatter" in e["code"]])
        # config-provided values silence the warning
        res = V.validate(p, doctype=dt, config={"frontmatter": {"supervisor": ["X"], "degree": "MSc", "institution": "U", "department": "D", "declaration": True}})
        warn = " ".join(w["message"] for w in res["warnings"] if w["code"] == "frontmatter-missing")
        for field in ("supervisor", "degree", "institution", "declaration"):
            self.assertNotIn("no %s" % field, warn)
        # the plain thesis doctype never warns about front matter
        res = V.validate(p, doctype=C.load_yaml(os.path.join(H.DOCTYPES, "thesis.yaml")), config={})
        self.assertFalse([w for w in res["warnings"] if w["code"] == "frontmatter-missing"])

    def test_default_thesis_path_unchanged(self):
        golden = os.path.join(H.FIXTURES, "golden", "thesis.tex")
        root, d = H.approved_project("", "thesis")
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(ms("md_to_latex.py", cwd=root)[0], 0)
        tex = C.read_text(os.path.join(d, ".ms", "latex", "demo.tex"))
        self.assertEqual(tex, C.read_text(golden))
        self.assertNotIn("frontmatter-metadata.json", os.listdir(os.path.join(d, ".ms", "latex")))
        self.assertNotIn("titlepage", tex)


if __name__ == "__main__":
    unittest.main()
