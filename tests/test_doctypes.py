"""Every doctype file is well-formed; each generic doctype added after the original four compiles to a PDF."""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers as H
import layout as L
import ms_common as C

SCRIPTS = os.path.join(H.ROOT, "scripts")
HAVE = {t: bool(shutil.which(t)) for t in ("pandoc", "tectonic", "pdftotext")}
NEW = ["literature-review", "project-report", "experiment-report", "research-proposal", "dissertation-proposal",
       "system-design-document", "case-study", "white-paper", "policy-brief", "conference-paper"]
ALL = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(H.DOCTYPES, "*.yaml")))


def ms(*args, cwd):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, args[0])] + list(args[1:]), cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def first_alts(items):
    return [str(i).split("|")[0].strip() for i in items]


class DoctypeFiles(unittest.TestCase):
    def test_new_doctypes_present(self):
        for n in NEW:
            self.assertIn(n, ALL)

    def test_every_doctype_is_valid(self):
        for n in ALL:
            with self.subTest(doctype=n):
                dt = C.load_yaml(os.path.join(H.DOCTYPES, n + ".yaml"))
                self.assertEqual(dt.get("name"), n)
                self.assertTrue(dt.get("description"))
                self.assertIn(dt.get("top_level_division"), ("section", "chapter"))
                self.assertIsInstance(dt.get("require_abstract"), bool)
                self.assertTrue(os.path.isfile(os.path.join(H.ROOT, dt.get("latex_defaults", "templates/latex/article.yaml"))))
                for key in ("pandoc_template",):
                    if dt.get(key):
                        self.assertTrue(os.path.isfile(os.path.join(H.ROOT, dt[key])))
                for key in ("required_sections", "recommended_sections"):
                    v = dt.get(key, [])
                    self.assertIsInstance(v, list)
                    for s in v:
                        self.assertTrue(all(a.strip() for a in str(s).split("|")), s)
                self.assertTrue(dt.get("required_sections"))
                self.assertEqual(L.check_config(dt, {}, skill_dir=H.ROOT), [])
                style = dt.get("citation_style")
                if style:
                    self.assertIn(style, L.CITATION_STYLES)

    def test_new_doctypes_have_sections_and_unique_names(self):
        for n in NEW:
            dt = C.load_yaml(os.path.join(H.DOCTYPES, n + ".yaml"))
            self.assertTrue(dt.get("recommended_sections"), n)
            self.assertTrue(dt["require_abstract"], n)
            self.assertTrue(any("|" in s for s in dt["required_sections"]), n)


    def test_common_alternative_headings_satisfy_required_sections(self):
        import validate_markdown as V
        cases = {
            "experiment-report": ["Introduction", "Materials and Methods", "Results and Discussion", "Conclusion and Future Work", "References"],
            "research-proposal": ["Introduction", "Aims and Objectives", "Research Design and Methods", "Work Plan", "References"],
            "dissertation-proposal": ["Introduction", "Literature Review", "Aims and Objectives", "Research Methods", "Timeline", "References"],
            "thesis-formal": ["Introduction", "Background", "Materials and Methods", "Results and Discussion", "Discussion", "Conclusion and Future Work", "References"],
            "project-report": ["Introduction", "Methods", "Results and Discussion", "Conclusion and Future Work", "References"],
        }
        for name, heads in cases.items():
            with self.subTest(doctype=name):
                dt = C.load_yaml(os.path.join(H.DOCTYPES, name + ".yaml"))
                body = "\n".join("# %s\n\nSome text here.\n" % h for h in heads)
                path = os.path.join(tempfile.mkdtemp(prefix="ms_alt_"), "r.md")
                with open(path, "w", encoding="utf-8") as f:
                    f.write('---\ntitle: T\nabstract: A\n---\n\n' + body)
                res = V.validate(path, doctype=dt)
                self.assertEqual([e for e in res["errors"] if e["code"] == "missing-required-section"], [])


@unittest.skipUnless(HAVE["pandoc"] and HAVE["tectonic"] and HAVE["pdftotext"], "pandoc/tectonic/poppler missing")
class DoctypePipeline(unittest.TestCase):
    def run_one(self, name):
        dt = C.load_yaml(os.path.join(H.DOCTYPES, name + ".yaml"))
        titles = first_alts(dt["required_sections"])
        root = tempfile.mkdtemp(prefix="ms_dt_")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.assertEqual(ms("ms_state.py", "init", "demo", "--doctype", name, cwd=root)[0], 0)
        d = os.path.join(root, "manuscript", "demo")
        shutil.copy(os.path.join(H.FIXTURES, "valid_project", "refs.bib"), os.path.join(d, ".ms", "references.bib"))
        with open(os.path.join(d, "plan.md"), "w", encoding="utf-8") as f:
            f.write("# Plan\n\n## Approved structure\n" + "".join("- %s\n" % t for t in titles))
        body = ["---", 'title: "Doctype Fixture %s"' % name, 'author: "Test Author"', "abstract: |",
                "  This is a test abstract.", "---", ""]
        for i, t in enumerate(titles):
            if t.lower() in ("references", "bibliography", "sources"):
                body += ["# %s" % t, ""]
                continue
            body += ["# %s" % t, "", "Prior work [@smith2020] and @lee2018 are relevant here, section %d." % (i + 1), ""]
            if i == 0:
                body += ["| Metric | Value |", "|--------|-------|", "| A      | 1     |", "", "Table: Summary {#tbl-res}", ""]
        with open(os.path.join(d, "demo-report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(body))
        for s in ["DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL"]:
            self.assertEqual(ms("ms_state.py", "stage", s, cwd=root)[0], 0)
        self.assertEqual(ms("ms_state.py", "approve-plan", "--phrase", "APPROVE PLAN", cwd=root)[0], 0)
        for s in ["EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"]:
            self.assertEqual(ms("ms_state.py", "stage", s, cwd=root)[0], 0)
        rc, out = ms("validate_markdown.py", cwd=root)
        self.assertEqual(rc, 0, out)
        rc, out = ms("ms_state.py", "approve-markdown", "--phrase", "APPROVE MARKDOWN", cwd=root)
        self.assertEqual(rc, 0, out)
        rc, out = ms("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        tex = os.path.join(d, ".ms", "latex", "demo.tex")
        rc, out = ms("validate_latex.py", tex, cwd=root)
        self.assertEqual(rc, 0, out)
        r = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pdf = os.path.join(d, ".ms", "latex", "demo.pdf")
        self.assertTrue(os.path.getsize(pdf) > 1000)
        text = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True).stdout
        self.assertIn(titles[0], text)
        if dt.get("layout", {}).get("columns") == 2:
            self.assertIn("twocolumn", C.read_text(tex))

    def test_new_doctypes_compile(self):
        for n in NEW:
            with self.subTest(doctype=n):
                self.run_one(n)


if __name__ == "__main__":
    unittest.main()
