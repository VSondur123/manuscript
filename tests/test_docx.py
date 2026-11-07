"""Optional DOCX export from the approved Markdown snapshot: refusals, content, layout, citations, validation, publish."""
import html
import json
import os
import re
import shutil
import unittest
import zipfile

import helpers as H
import ms_common as C
import ms_state as S
import validate_docx as V

HAVE_PANDOC = bool(shutil.which("pandoc"))
run = H.run_script


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f)


def docx_xml(path, part="word/document.xml"):
    with zipfile.ZipFile(path) as z:
        return z.read(part).decode("utf-8")


def text_of(xml):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", xml)))


def approve_with(extra_before_conclusion="", **kw):
    """approved_project, but with extra Markdown spliced into the report BEFORE approval."""
    root, d = H.approved_project(approve=False, **kw)
    rp = os.path.join(d, "demo-report.md")
    text = C.read_text(rp).replace("# Conclusion", extra_before_conclusion + "\n# Conclusion", 1)
    with open(rp, "w", encoding="utf-8") as f:
        f.write(text)
    for s in ["DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL"]:
        run("ms_state.py", "stage", s, cwd=root)
    run("ms_state.py", "approve-plan", "--phrase", "APPROVE PLAN", cwd=root)
    for s in ["EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"]:
        run("ms_state.py", "stage", s, cwd=root)
    run("validate_markdown.py", cwd=root)
    rc, out = run("ms_state.py", "approve-markdown", "--phrase", "APPROVE MARKDOWN", cwd=root)
    assert rc == 0, out
    return root, d


@unittest.skipUnless(HAVE_PANDOC, "pandoc not installed")
class DocxExport(unittest.TestCase):
    def tearDown(self):
        for r in getattr(self, "roots", []):
            shutil.rmtree(r, ignore_errors=True)

    def project(self, **kw):
        root, d = H.approved_project(**kw)
        self.roots = getattr(self, "roots", []) + [root]
        return root, d

    def state(self, d):
        return load_json(os.path.join(d, ".ms", "state.json"))

    def test_refuses_when_not_approved(self):
        root, d = self.project(approve=False)
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 2, out)
        self.assertIn("not currently approved", out)
        self.assertFalse(os.path.exists(os.path.join(d, ".ms", "docx", "demo.docx")))

    def test_refuses_after_draft_edit_and_never_reads_draft(self):
        root, d = self.project()
        with open(os.path.join(d, "demo-report.md"), "a", encoding="utf-8") as f:
            f.write("\nDRAFT-ONLY-SENTENCE\n")
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 2, out)
        self.assertFalse(os.path.exists(os.path.join(d, ".ms", "docx", "demo.docx")))

    def test_refuses_when_snapshot_altered(self):
        root, d = self.project()
        snap = os.path.join(d, self.state(d)["markdown_approval"]["snapshot"])
        os.chmod(snap, 0o644)
        with open(snap, "a", encoding="utf-8") as f:
            f.write("\ntampered\n")
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 2, out)
        self.assertIn("snapshot", out)

    def test_default_export_is_valid_and_recorded(self):
        root, d = self.project()
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        docx = os.path.join(d, ".ms", "docx", "demo.docx")
        st = self.state(d)
        self.assertEqual(st["stage"], "MARKDOWN_APPROVED")  # not a gate: no new stage
        rec = st["docx"]
        self.assertEqual(rec["sha256"], C.sha256_file(docx))
        self.assertEqual(rec["from_approved_sha256"], st["markdown_approval"]["sha256"])
        self.assertTrue(rec["inputs"]["csl"]["sha256"])
        snap = C.read_text(os.path.join(d, st["markdown_approval"]["snapshot"]))
        res = V.validate(docx, snap)
        self.assertEqual(res["errors"], [], res)
        self.assertEqual(res["stats"]["images"], 1)
        self.assertEqual(res["stats"]["tables"], 1)
        xml = docx_xml(docx)
        txt = text_of(xml)
        self.assertIn("A Fixture Report", txt)
        self.assertIn("Figure 1", txt)       # cross-reference resolved by the Lua filter
        self.assertIn("Table 1", txt)
        self.assertIn("Figure 1. System architecture", txt)
        self.assertIn("Table 1. Results summary", txt)
        self.assertNotIn("(?)", txt)
        self.assertNotIn("@smith2020", txt)
        self.assertIn("A study of fixtures", txt)   # reference list entry
        self.assertIn("1 Introduction", txt)         # numbered headings (article default)
        self.assertEqual(run("ms_state.py", "verify", cwd=root)[0], 0)

    def test_apa7_and_layout(self):
        root, d = self.project(config_extra="citation_style: apa7\nlayout:\n  paper: letter\n  font_size: 12\n  spacing: double\n"
                               "  margins: 1in\n  font: times\n  page_numbers: bottom-right\n  heading_numbering: off\n  columns: 2\n  table_style: plain")
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertIn("IGNORED: layout.columns", out)
        self.assertIn("IGNORED: layout.table_style", out)
        docx = os.path.join(d, ".ms", "docx", "demo.docx")
        doc = docx_xml(docx)
        self.assertIn('w:w="12240" w:h="15840"', doc)                        # letter
        self.assertRegex(doc, r'w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"')
        sty = docx_xml(docx, "word/styles.xml")
        self.assertRegex(sty, r'<w:sz w:val="24" /><w:szCs w:val="24" />')    # 12 pt
        self.assertIn('w:line="480" w:lineRule="auto"', sty)                 # double
        self.assertIn('w:ascii="Times New Roman"', sty)
        self.assertIn("PAGE", docx_xml(docx, "word/footer1.xml"))
        self.assertIn('w:val="right"', docx_xml(docx, "word/footer1.xml"))
        txt = text_of(doc)
        self.assertIn("Smith & Doe, 2020", txt)                              # APA author-year in text
        self.assertIn("Lee (", txt)
        self.assertNotRegex(txt, r"\[\d\]")                                  # not numeric
        self.assertNotIn("1 Introduction", txt)                              # numbering off
        self.assertEqual(self.state(d)["docx"]["inputs"]["csl"]["path"], "templates/csl/apa.csl")

    def test_bibtex_path_styles_have_csl(self):
        for style, needle in (("numeric", "[1]"), ("ieee", "[1]"), ("author-year", "Smith")):
            root, d = self.project(config_extra="citation_style: %s" % style)
            rc, out = run("md_to_docx.py", cwd=root)
            self.assertEqual(rc, 0, out)
            txt = text_of(docx_xml(os.path.join(d, ".ms", "docx", "demo.docx")))
            self.assertIn(needle, txt, style)
            self.assertNotIn("(?)", txt)

    def test_math_and_unresolved_reference(self):
        root, d = approve_with("\n# Model\n\nThe energy is\n\n$$E = mc^2$$\n\nSee [Figure](#fig-arch).\n")
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        docx = os.path.join(d, ".ms", "docx", "demo.docx")
        self.assertIn("<m:oMath", docx_xml(docx))
        self.assertEqual(V.validate(docx, C.read_text(os.path.join(d, self.state(d)["markdown_approval"]["snapshot"])))["errors"], [])

    def test_unresolved_reference_is_reported_by_filter(self):
        import subprocess
        r = subprocess.run(["pandoc", "-f", "markdown", "-t", "docx", "--lua-filter", os.path.join(H.ROOT, "templates", "docx", "ms-docx.lua"),
                            "-o", os.devnull], input="# A\n\nSee [Figure](#fig-nowhere).\n", capture_output=True, text=True)
        self.assertIn("MS-UNRESOLVED-REF fig-nowhere", r.stderr)

    def test_venue_doctype_generic_styling_notice(self):
        root, d = self.project(doctype="ieee-report")
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertIn("NOT reproduced", out)
        self.assertTrue(os.path.isfile(os.path.join(d, ".ms", "docx", "demo.docx")))

    def test_thesis_formal_cover_abstract_toc(self):
        root, d = self.project(doctype="thesis-formal", config_after=(
            'frontmatter:\n  institution: "Test University"\n  degree: "Master of Science"\n  supervisor: "Dr. A. Person"\n'
            "  lof: true\n  declaration: true"))
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        docx = os.path.join(d, ".ms", "docx", "demo.docx")
        xml = docx_xml(docx)
        txt = text_of(xml)
        for needle in ("Test University", "Master of Science", "Supervisor: Dr. A. Person", "This is a test abstract."):
            self.assertIn(needle, txt)
        self.assertIn("TOC", xml)                                            # table of contents field
        self.assertIn("roman front-matter numbering", out)
        self.assertIn("IGNORED: frontmatter.lof", out)
        self.assertIn("IGNORED: frontmatter.declaration", out)

    def test_thesis_formal_without_config_still_gets_toc_and_notice(self):
        root, d = self.project(doctype="thesis-formal")
        rc, out = run("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertIn("lettered appendices", out)
        xml = docx_xml(os.path.join(d, ".ms", "docx", "demo.docx"))
        self.assertIn("TOC", xml)
        self.assertIn("This is a test abstract.", text_of(xml))

    def test_publish_refuses_after_draft_edit(self):
        root, d = self.project()
        run("md_to_docx.py", cwd=root)
        with open(os.path.join(d, "demo-report.md"), "a", encoding="utf-8") as f:
            f.write("\nEdited after export.\n")
        rc, out = run("ms_state.py", "publish", "--docx-only", cwd=root)
        self.assertEqual(rc, 2, out)
        self.assertIn("not current", out)
        self.assertFalse(os.path.exists(os.path.join(d, "demo.docx")))

    def test_real_reapproval_makes_docx_stale(self):
        root, d = self.project()
        run("md_to_docx.py", cwd=root)
        with open(os.path.join(d, "demo-report.md"), "a", encoding="utf-8") as f:
            f.write("\nEdited after export.\n")
        run("ms_state.py", "verify", "--fix", cwd=root)
        run("ms_state.py", "sync", cwd=root)
        st = self.state(d)
        for s in ["MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"]:
            if S.IDX[st["stage"]] < S.IDX[s]:
                run("ms_state.py", "stage", s, cwd=root)
        run("validate_markdown.py", cwd=root)
        rc, out = run("ms_state.py", "approve-markdown", "--phrase", "APPROVE MARKDOWN", cwd=root)
        self.assertEqual(rc, 0, out)
        rc, out = run("ms_state.py", "verify", cwd=root)
        self.assertIn("docx_stale", out)
        self.assertEqual(run("ms_state.py", "publish", "--docx-only", cwd=root)[0], 2)
        self.assertEqual(run("md_to_docx.py", cwd=root)[0], 0)   # re-export clears it
        self.assertNotIn("docx_stale", run("ms_state.py", "verify", cwd=root)[1])

    def test_validator_detects_damage(self):
        root, d = self.project()
        run("md_to_docx.py", cwd=root)
        docx = os.path.join(d, ".ms", "docx", "demo.docx")
        snap = C.read_text(os.path.join(d, self.state(d)["markdown_approval"]["snapshot"]))
        # remove a heading and the image, corrupt nothing else
        bad = os.path.join(root, "bad.docx")
        with zipfile.ZipFile(docx) as zi, zipfile.ZipFile(bad, "w") as zo:
            for it in zi.infolist():
                data = zi.read(it.filename)
                if it.filename == "word/document.xml":
                    s = data.decode("utf-8")
                    s = s.replace("Methodology", "Something else")
                    s = re.sub(r"<w:drawing>.*?</w:drawing>", "", s, flags=re.S)
                    data = s.encode("utf-8")
                zo.writestr(it, data)
        res = V.validate(bad, snap)
        joined = " ".join(res["errors"])
        self.assertIn("Methodology", joined)
        self.assertIn("image", joined)
        broken = os.path.join(root, "broken.docx")
        with zipfile.ZipFile(docx) as zi, zipfile.ZipFile(broken, "w") as zo:
            for it in zi.infolist():
                data = zi.read(it.filename)
                zo.writestr(it, b"<w:document><oops>" if it.filename == "word/document.xml" else data)
        self.assertTrue(any("not well-formed" in e for e in V.validate(broken, snap)["errors"]))
        self.assertTrue(V.validate(os.path.join(root, "nonexistent.docx"))["errors"])

    def test_publish_docx_and_stale_detection(self):
        root, d = self.project()
        run("md_to_docx.py", cwd=root)
        # default publish never copies the docx
        os.makedirs(os.path.join(d, ".ms", "latex"), exist_ok=True)
        for ext in ("tex", "pdf"):
            with open(os.path.join(d, ".ms", "latex", "demo." + ext), "w") as f:
                f.write("x")
        p = os.path.join(d, ".ms", "state.json")
        st = load_json(p); st["stage"] = "COMPLETED"; save_json(p, st)
        rc, out = run("ms_state.py", "publish", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(d, "demo.docx")))
        rc, out = run("ms_state.py", "publish", "--docx", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertIn("demo.docx", out)
        self.assertEqual(C.sha256_file(os.path.join(d, "demo.docx")), C.sha256_file(os.path.join(d, ".ms", "docx", "demo.docx")))
        # approval changed since export -> verify flags it and publish --docx refuses
        st = load_json(p); st["docx"]["from_approved_sha256"] = "0" * 64; save_json(p, st)
        rc, out = run("ms_state.py", "verify", cwd=root)
        self.assertIn("docx_stale", out)
        rc, out = run("ms_state.py", "publish", "--docx", cwd=root)
        self.assertEqual(rc, 2, out)
        self.assertIn("earlier Markdown approval", out)

    def test_publish_docx_only_and_missing_export(self):
        root, d = self.project()
        rc, out = run("ms_state.py", "publish", "--docx-only", cwd=root)
        self.assertEqual(rc, 2, out)
        self.assertIn("no DOCX export", out)
        run("md_to_docx.py", cwd=root)
        rc, out = run("ms_state.py", "publish", "--docx-only", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(os.path.join(d, "demo.docx")))
        self.assertFalse(os.path.exists(os.path.join(d, "demo.tex")))

    def test_docx_flagged_after_reapproval_changes(self):
        root, d = self.project()
        run("md_to_docx.py", cwd=root)
        with open(os.path.join(d, "demo-report.md"), "a", encoding="utf-8") as f:
            f.write("\nExtra sentence.\n")
        rc, out = run("ms_state.py", "verify", cwd=root)
        self.assertIn("approval_stale", out)


if __name__ == "__main__":
    unittest.main()
