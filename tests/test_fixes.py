"""Regression tests for the checker's defects: plain tables in two columns, one-page thesis cover, map authors,
sibling-PNG locking, MLA narrative cites, inert raw TeX, logo confinement, compile exit status, Word CSL note, script modes."""
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

import helpers as H
import layout as L
import ms_common as C
import validate_markdown as V
from test_thesis_frontmatter import CONFIG, formal_project, approve as approve_formal, ms

SCRIPTS = os.path.join(H.ROOT, "scripts")
HAVE = {t: bool(shutil.which(t)) for t in ("pandoc", "tectonic", "pdftotext")}
FULL = HAVE["pandoc"] and HAVE["tectonic"] and HAVE["pdftotext"]
NEED_PDF = unittest.skipUnless(FULL, "pandoc/tectonic/poppler missing")
NEED_PANDOC = unittest.skipUnless(HAVE["pandoc"], "pandoc not installed")


def compile_tex(tex):
    r = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex, "tectonic"], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def pdf_pages(pdf):
    out = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True).stdout
    return out.split("\f")


def project(config_extra="", edit=None, doctype="research-report"):
    """Approved fixture project whose report is edited (text -> text) BEFORE approval."""
    root, d = H.approved_project(config_extra, doctype, approve=False)
    rp = os.path.join(d, "demo-report.md")
    if edit:
        new = edit(C.read_text(rp))
        with open(rp, "w", encoding="utf-8") as f:
            f.write(new)
    approve_formal(root, d)
    return root, d


class PlainTablesTwoColumns(unittest.TestCase):
    @NEED_PDF
    def test_plain_table_style_compiles_in_both_modes(self):
        for cfg in ("layout:\n  columns: 2\n  table_style: plain", "layout:\n  table_style: plain"):
            with self.subTest(cfg=cfg):
                root, d = project(cfg)
                self.addCleanup(shutil.rmtree, root, True)
                rc, out = H.run_script("md_to_latex.py", cwd=root)
                self.assertEqual(rc, 0, out)
                rc, out = compile_tex(os.path.join(d, ".ms", "latex", "demo.tex"))
                self.assertEqual(rc, 0, out)


class ThesisCoverOnePage(unittest.TestCase):
    @NEED_PDF
    def test_full_cover_fits_one_page(self):
        cfg = CONFIG + "\n  faculty: Faculty of Engineering and Applied Sciences"
        root, d = formal_project(config=cfg)
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(ms("ms_state.py", "lock-logo", cwd=root)[0], 0)
        approve_formal(root, d)
        rc, out = ms("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        tex = os.path.join(d, ".ms", "latex", "demo.tex")
        rc, out = compile_tex(tex)
        self.assertEqual(rc, 0, out)
        pages = pdf_pages(tex[:-4] + ".pdf")
        self.assertIn("1 November 2026", pages[0])
        self.assertNotIn("1 November 2026", pages[1])
        first = [l for l in pages[1].splitlines() if l.strip()][0]
        self.assertNotIn("November", first)


class MapAuthors(unittest.TestCase):
    EDIT = staticmethod(lambda t: re.sub(r"^author:.*$", 'author:\n  - name: Ann Lee\n    affiliation: Example University\n  - name: Bo Chen\n    affiliation: Other Institute',
                                          t, count=1, flags=re.M))

    @NEED_PANDOC
    def test_map_authors_become_name_with_affiliation(self):
        root, d = project(edit=self.EDIT)
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = H.run_script("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        tex = C.read_text(os.path.join(d, ".ms", "latex", "demo.tex"))
        self.assertIn("Ann Lee (Example University)", tex)
        self.assertIn("Bo Chen (Other Institute)", tex)
        self.assertNotRegex(tex, r"\\author\{[^}]*true")

    @NEED_PANDOC
    def test_string_authors_do_not_use_the_filter(self):
        root, d = project()
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = H.run_script("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("flatten-authors", C.read_text(os.path.join(d, ".ms", "logs", "latex-generation.log")))


class SiblingPngLocked(unittest.TestCase):
    @NEED_PANDOC
    def test_pdf_figure_sibling_png_is_hash_locked(self):
        def edit(t):
            return t.rstrip("\n") + "\n\n![Vector figure](.ms/figures/vec.pdf){#fig-vec}\n\nSee [Figure](#fig-vec).\n"
        root, d = H.approved_project(approve=False)
        figs = os.path.join(d, ".ms", "figures")
        shutil.copy(os.path.join(figs, "arch.png"), os.path.join(figs, "vec.png"))
        with open(os.path.join(figs, "vec.pdf"), "wb") as f:
            f.write(b"%PDF-1.4\n%fake\n")
        rp = os.path.join(d, "demo-report.md")
        new = edit(C.read_text(rp))
        with open(rp, "w", encoding="utf-8") as f:
            f.write(new)
        self.addCleanup(shutil.rmtree, root, True)
        approve_formal(root, d)
        st = json.load(open(os.path.join(d, ".ms", "state.json")))
        self.assertIn(".ms/figures/vec.png", st["markdown_approval"]["figures"])
        rc, out = H.run_script("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        with open(os.path.join(figs, "vec.png"), "ab") as f:
            f.write(b"tampered")
        rc, out = H.run_script("ms_state.py", "verify", cwd=root)
        self.assertIn("vec.png", out)
        self.assertIn("figure_changed", out)
        rc, out = H.run_script("md_to_docx.py", cwd=root)
        self.assertNotEqual(rc, 0, out)

    def test_pdf_to_png_refuses_unlocked_sibling(self):
        import md_to_docx as D
        d = tempfile.mkdtemp(prefix="ms_pdf_")
        self.addCleanup(shutil.rmtree, d, True)
        open(os.path.join(d, "f.pdf"), "wb").write(b"x")
        open(os.path.join(d, "f.png"), "wb").write(b"png")
        import ms_state as S
        with self.assertRaises(S.StateError):
            D.pdf_to_png("![c](f.pdf)", d, {})
        text, _ = D.pdf_to_png("![c](f.pdf)", d, {"f.png": C.sha256_file(os.path.join(d, "f.png"))})
        self.assertIn("f.png", text)


class MlaNarrative(unittest.TestCase):
    def test_validator_warns_for_narrative_cite_without_locator(self):
        fx = os.path.join(H.FIXTURES, "valid_project")
        cfg = {"citation_style": "mla9"}
        res = V.validate(os.path.join(fx, "draft.md"), os.path.join(fx, "refs.bib"), config=cfg, base_dir=fx)
        self.assertIn("mla-narrative-no-locator", H.codes(res, "warnings"))
        self.assertEqual(H.codes(res, "errors"), [])
        text = C.read_text(os.path.join(fx, "draft.md")).replace("@lee2018 and describe", "@lee2018 [p. 5] and describe")
        path = os.path.join(tempfile.mkdtemp(prefix="ms_mla_"), "r.md")
        open(path, "w", encoding="utf-8").write(text)
        res = V.validate(path, os.path.join(fx, "refs.bib"), config=cfg, base_dir=fx)
        self.assertNotIn("mla-narrative-no-locator", H.codes(res, "warnings"))
        res = V.validate(os.path.join(fx, "draft.md"), os.path.join(fx, "refs.bib"), base_dir=fx)  # other styles: no warning
        self.assertNotIn("mla-narrative-no-locator", H.codes(res, "warnings"))

    @NEED_PANDOC
    def test_no_empty_parentheses_in_latex_or_word(self):
        root, d = H.approved_project("citation_style: mla9")
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = H.run_script("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        tex = C.read_text(os.path.join(d, ".ms", "latex", "demo.tex"))
        self.assertNotIn("{})", tex.replace("\\citeproc{ref-lee2018}{Lee})", ""))
        self.assertIn("approach of Lee and", re.sub(r"\s+", " ", tex))
        rc, out = H.run_script("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        txt = subprocess.run(["pandoc", os.path.join(d, ".ms", "docx", "demo.docx"), "-t", "plain"], capture_output=True, text=True).stdout
        self.assertNotIn("Lee ()", txt)
        self.assertNotIn("citation_style numeric", out)


class RawTexIsInert(unittest.TestCase):
    EDIT = staticmethod(lambda t: t.replace("# Methodology", "\\input{/etc/passwd}\n\n\\immediate\\write18{echo pwned}\n\n# Methodology", 1))

    def test_validator_warns(self):
        path = os.path.join(tempfile.mkdtemp(prefix="ms_raw_"), "r.md")
        fx = os.path.join(H.FIXTURES, "valid_project")
        text = C.read_text(os.path.join(fx, "draft.md"))
        open(path, "w", encoding="utf-8").write(self.EDIT(text) + "\nMath $\\input{x}$ and `\\input{y}` are fine.\n")
        res = V.validate(path, os.path.join(fx, "refs.bib"), base_dir=fx)
        self.assertEqual(H.codes(res, "warnings").count("raw-latex-ignored"), 1)
        self.assertIn("not passed through", [w for w in res["warnings"] if w["code"] == "raw-latex-ignored"][0]["message"])
        clean = V.validate(os.path.join(fx, "draft.md"), os.path.join(fx, "refs.bib"), base_dir=fx)
        self.assertNotIn("raw-latex-ignored", H.codes(clean, "warnings"))

    @NEED_PDF
    def test_input_is_not_a_command_and_compile_does_not_read_the_file(self):
        root, d = project(edit=self.EDIT)
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = H.run_script("md_to_latex.py", cwd=root)
        self.assertEqual(rc, 0, out)
        tex = C.read_text(os.path.join(d, ".ms", "latex", "demo.tex"))
        self.assertNotRegex(tex, r"(?<!textbackslash\{\})\\input\{")
        self.assertNotRegex(tex, r"(?<!textbackslash\{\})\\(?:immediate|write)\b")
        self.assertIn("textbackslash", tex)
        rc, out = H.run_script("md_to_latex.py", "--preview", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertNotRegex(C.read_text(os.path.join(d, ".ms", "latex", "demo-preview.tex")), r"(?<!textbackslash\{\})\\input\{")
        rc, out = compile_tex(os.path.join(d, ".ms", "latex", "demo.tex"))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("nobody", "\n".join(pdf_pages(os.path.join(d, ".ms", "latex", "demo.pdf"))))

    @NEED_PANDOC
    def test_docx_ignores_raw_tex(self):
        root, d = project(edit=self.EDIT)
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = H.run_script("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        txt = subprocess.run(["pandoc", os.path.join(d, ".ms", "docx", "demo.docx"), "-t", "plain"], capture_output=True, text=True).stdout
        self.assertNotIn("nobody", txt)


class LogoConfinement(unittest.TestCase):
    def setUp(self):
        self.root, self.d = formal_project(config=CONFIG)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_config_rejects_absolute_logo(self):
        dt = C.load_yaml(os.path.join(H.DOCTYPES, "thesis-formal.yaml"))
        for bad in ("/etc/hosts.png", "~/x.png"):
            errs = L.check_config(dt, {"frontmatter": {"logo": bad}})
            self.assertTrue(any("frontmatter.logo" in e for e in errs), (bad, errs))

    def test_lock_logo_file_rules(self):
        outside = os.path.join(tempfile.mkdtemp(prefix="ms_out_"), "o.png")
        shutil.copy(os.path.join(self.d, "logo.png"), outside)
        rc, out = ms("ms_state.py", "lock-logo", "--file", outside, cwd=self.root)
        self.assertNotEqual(rc, 0)
        self.assertIn("outside the project", out)
        link = os.path.join(self.d, "evil.png")
        os.symlink("/etc/hosts", link)
        rc, out = ms("ms_state.py", "lock-logo", "--file", "evil.png", cwd=self.root)
        self.assertNotEqual(rc, 0)
        self.assertIn("outside the project", out)
        rc, out = ms("ms_state.py", "lock-logo", "--file", os.path.join(self.d, "logo.png"), cwd=self.root)  # absolute but inside: fine
        self.assertEqual(rc, 0, out)
        rc, out = ms("ms_state.py", "lock-logo", cwd=self.root)  # from config: relative, inside
        self.assertEqual(rc, 0, out)


class CompileExitStatus(unittest.TestCase):
    def test_nonzero_engine_exit_fails_even_with_a_pdf(self):
        bindir = tempfile.mkdtemp(prefix="ms_bin_")
        self.addCleanup(shutil.rmtree, bindir, True)
        eng = os.path.join(bindir, "faketex")
        with open(eng, "w") as f:
            f.write('#!/bin/sh\nfor a in "$@"; do case "$a" in *.tex) n="${a%.tex}";; esac; done\necho %PDF-1.4 > "$n.pdf"\nexit 1\n')
        os.chmod(eng, 0o755)
        work = tempfile.mkdtemp(prefix="ms_ct_")
        self.addCleanup(shutil.rmtree, work, True)
        os.makedirs(os.path.join(work, "latex"))
        tex = os.path.join(work, "latex", "a.tex")
        open(tex, "w").write("\\documentclass{article}\\begin{document}x\\end{document}")
        r = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex, "faketex"], capture_output=True, text=True,
                           env=dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"]))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("COMPILE FAILED", r.stdout)
        self.assertIn("# exit: 1", C.read_text(os.path.join(work, "logs", "compile.log")))

    @NEED_PDF
    def test_good_and_broken_documents(self):
        work = tempfile.mkdtemp(prefix="ms_ct_")
        self.addCleanup(shutil.rmtree, work, True)
        os.makedirs(os.path.join(work, "latex"))
        tex = os.path.join(work, "latex", "a.tex")
        open(tex, "w").write("\\documentclass{article}\\begin{document}x\\end{document}")
        self.assertEqual(compile_tex(tex)[0], 0)
        open(tex, "w").write("\\documentclass{article}\\begin{document}\\undefinedcommandxyz\\end{document}")
        self.assertEqual(compile_tex(tex)[0], 1)
        self.assertFalse(os.path.exists(tex[:-4] + ".pdf"))


class WordCslNote(unittest.TestCase):
    @NEED_PANDOC
    def test_note_when_word_csl_differs_from_pdf_bibtex_style(self):
        root, d = H.approved_project()
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = H.run_script("md_to_docx.py", cwd=root)
        self.assertEqual(rc, 0, out)
        self.assertIn("may differ from the PDF", out)
        st = json.load(open(os.path.join(d, ".ms", "state.json")))
        self.assertTrue(any("may differ from the PDF" in n for n in st["docx"]["inputs"]["notes"]))


class ScriptModes(unittest.TestCase):
    def test_scripts_are_executable(self):
        for n in ("md_to_docx.py", "style_scan.py", "validate_docx.py"):
            self.assertTrue(os.stat(os.path.join(SCRIPTS, n)).st_mode & stat.S_IXUSR, n)


if __name__ == "__main__":
    unittest.main()
