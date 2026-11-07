"""Venue/publisher doctypes: the real pipeline (init -> draft with venue front matter -> validate -> approve ->
md_to_latex -> validate_latex -> compile) produces a PDF containing the title and authors. Skipped when tools are missing.
Compiling needs tectonic's bundle (network on first use for each class)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers as H
import ms_common as C

SCRIPTS = os.path.join(H.ROOT, "scripts")
HAVE = {t: bool(shutil.which(t)) for t in ("pandoc", "tectonic", "pdftotext")}

TITLE = "Venue Template Fixture Study"

FRONT_MULTI = """---
title: "%s"
author:
  - name: Alice Venue
    affiliation: Department of Testing, Example University
    email: alice@example.org
    city: Zurich
    country: Switzerland
  - name: Bob Layout
    affiliation: Department of Testing, Example University
    email: bob@example.org
    city: Zurich
    country: Switzerland
  - name: Carol Mark
    affiliation: Institute of Typesetting, Other Institute
    email: carol@example.org
    city: Oslo
    country: Norway
abstract: |
  This is a test abstract.
keywords: [templates, pandoc, testing]
%s---
"""

VENUES = {
    "acm-paper": ("", ["acmart", "ACM-Reference-Format"]),
    "llncs-paper": ("", ["llncs", "splncs04", "\\inst{1}", "\\inst{2}"]),
    "elsevier-paper": ("journal: Journal of Fixtures\n", ["elsarticle", "elsarticle-num", "\\affiliation[2]"]),
    "revtex-paper": ("", ["revtex4-2", "apsrev4-2"]),
    "preprint": ("", ["unsrtnat", "natbib"]),
}
# extra metadata that switches ACM into the full conference rights block
ACM_CONF = ("acm-conference: TEST '26\nacm-conference-name: Test Conference\nacm-date: June 2026\n"
            "acm-venue: Zurich, Switzerland\nacm-year: 2026\nacm-doi: 10.1145/0000000.0000000\nacm-isbn: 978-0-0000-0000-0/26/06\n")


def ms(*args, cwd):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, args[0])] + list(args[1:]), cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


@unittest.skipUnless(HAVE["pandoc"], "pandoc not installed")
class Venues(unittest.TestCase):
    def build(self, doctype, extra="", single_author=False):
        root = tempfile.mkdtemp(prefix="ms_venue_")
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = ms("ms_state.py", "init", "demo", "--doctype", doctype, cwd=root)
        self.assertEqual(rc, 0, out)
        d = os.path.join(root, "manuscript", "demo")
        H.install_fixture(d, "demo")
        p = os.path.join(d, "demo-report.md")
        body = C.read_text(p)
        body = re.sub(r"\A---.*?\n---\n", "", body, flags=re.S)
        front = FRONT_MULTI % (TITLE, extra)
        if single_author:
            front = re.sub(r"author:.*?abstract:", "author: Dana Solo\nabstract:", front, flags=re.S)
        with open(p, "w", encoding="utf-8") as f:
            f.write(front + body)
        for stages in (["DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL"],):
            for s in stages:
                self.assertEqual(ms("ms_state.py", "stage", s, cwd=root)[0], 0)
        rc, out = ms("ms_state.py", "approve-plan", "--phrase", "APPROVE PLAN", cwd=root)
        self.assertEqual(rc, 0, out)
        for s in ["EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"]:
            self.assertEqual(ms("ms_state.py", "stage", s, cwd=root)[0], 0)
        rc, out = ms("validate_markdown.py", cwd=root)
        self.assertEqual(rc, 0, out)
        rc, out = ms("ms_state.py", "approve-markdown", "--phrase", "APPROVE MARKDOWN", cwd=root)
        self.assertEqual(rc, 0, out)
        rc, out = ms("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        return root, d, os.path.join(d, ".ms", "latex", "demo.tex")

    def compile(self, tex):
        rc, out = ms("validate_latex.py", tex, cwd=os.path.dirname(tex))
        self.assertEqual(rc, 0, out)
        t = os.path.getmtime(tex) - 5  # compile_latex.sh's staleness check (-nt) has 1 s granularity
        os.utime(tex, (t, t))
        r = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex, "tectonic"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pdf = tex[:-4] + ".pdf"
        self.assertTrue(os.path.isfile(pdf))
        return subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout

    def test_each_venue_generates_expected_tex(self):
        for dt, (extra, needles) in VENUES.items():
            with self.subTest(doctype=dt):
                _, _, tex = self.build(dt, extra)
                text = C.read_text(tex)
                self.assertIn(TITLE, text)
                for n in needles:
                    self.assertIn(n, text)
                self.assertNotIn("\\begin{longtable}", text)  # tables go through the tabular filter
                self.assertIn("\\bibliography{references}", text)
                self.assertNotIn("\\citeproc", text)

    @unittest.skipUnless(HAVE["tectonic"] and HAVE["pdftotext"], "tectonic/poppler not installed")
    def test_each_venue_compiles_to_pdf_with_title_and_author(self):
        for dt, (extra, _) in VENUES.items():
            with self.subTest(doctype=dt):
                _, _, tex = self.build(dt, extra)
                text = self.compile(tex)
                flat = re.sub(r"\s+", " ", text)
                self.assertIn(TITLE.lower(), flat.lower())
                self.assertIn("alice venue", flat.lower())
                self.assertIn("test abstract", flat.lower())
                self.assertIn("Smith", flat)  # bibliography resolved through the class .bst
                self.assertNotIn("[?]", flat)
                self.assertNotIn("(?)", flat)
                self.assertNotIn("(author?)", flat)  # \citet must degrade gracefully with numeric .bst files
                self.assertEqual(flat.count("carol@example.org"), 1)

    @unittest.skipUnless(HAVE["tectonic"] and HAVE["pdftotext"], "tectonic/poppler not installed")
    def test_single_string_author_compiles(self):
        for dt in VENUES:
            with self.subTest(doctype=dt):
                _, _, tex = self.build(dt, "", single_author=True)
                flat = re.sub(r"\s+", " ", self.compile(tex))
                self.assertIn("dana solo", flat.lower())

    @unittest.skipUnless(HAVE["tectonic"] and HAVE["pdftotext"], "tectonic/poppler not installed")
    def test_acm_conference_rights_block(self):
        _, _, tex = self.build("acm-paper", ACM_CONF)
        text = C.read_text(tex)
        self.assertIn("\\acmConference[TEST '26]", text)
        self.assertNotIn("nonacm]", text)
        flat = re.sub(r"\s+", " ", self.compile(tex))
        self.assertIn("Test Conference", flat)


if __name__ == "__main__":
    unittest.main()
