"""Layout options and citation-style configuration: validation (no external tools), generated LaTeX, and real
tectonic compiles. Tests needing pandoc/tectonic/poppler skip when those tools are missing."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import helpers as H
import layout as L
import ms_common as C
import ms_state as S

SCRIPTS = os.path.join(H.ROOT, "scripts")
HAVE = {t: bool(shutil.which(t)) for t in ("pandoc", "tectonic", "pdftotext")}
NEED_PDF = unittest.skipUnless(HAVE["pandoc"] and HAVE["tectonic"] and HAVE["pdftotext"], "pandoc/tectonic/poppler missing")
NEED_PANDOC = unittest.skipUnless(HAVE["pandoc"], "pandoc not installed")


def compile_tex(tex):
    r = subprocess.run([os.path.join(SCRIPTS, "compile_latex.sh"), tex, "tectonic"], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def pdf_text(pdf):
    out = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True).stdout
    return re.sub(r"\s+", " ", out)


def generate(config_extra, doctype="research-report", config_after=""):
    root, d = H.approved_project(config_extra, doctype, config_after=config_after)
    rc, out = H.run_script("md_to_latex.py", cwd=root)
    return root, d, rc, out, os.path.join(d, ".ms", "latex", "demo.tex")


class LayoutValidation(unittest.TestCase):
    """Pure-Python: whitelist behaviour of scripts/layout.py."""

    def test_valid_values_and_yaml_coercion(self):
        cfg = C.parse_yaml("layout:\n  font_size: 12\n  columns: 2\n  heading_numbering: no\n  paper: letter\n  margins: 1in\n")
        self.assertEqual(L.resolve_layout({}, cfg), {"font_size": "12", "columns": "2", "heading_numbering": "off",
                                                    "paper": "letter", "margins": "1in"})

    def test_every_option_rejects_unlisted_value_and_lists_allowed(self):
        for key, allowed in L.LAYOUT_KEYS.items():
            with self.assertRaises(ValueError) as cm:
                L.resolve_layout({}, {"layout": {key: "bogus-value"}})
            msg = str(cm.exception)
            self.assertIn("layout.%s" % key, msg)
            if allowed:
                for a in allowed:
                    self.assertIn(a, msg)

    def test_margins_regex_blocks_injection(self):
        for good in ("2.5cm", "1in", "25mm", "0.75in", "3cm"):
            self.assertEqual(L.resolve_layout({}, {"layout": {"margins": good}})["margins"], good)
        for bad in ("2.5", "cm", "1in}\\input{/etc/passwd}", "2cm,showframe", "2cm\n\\x", "-1cm", "50cm", "1 in", "margin=2cm", "1in;"):
            with self.assertRaises(ValueError, msg=bad):
                L.resolve_layout({}, {"layout": {"margins": bad}})

    def test_unknown_key_and_bad_shape(self):
        with self.assertRaises(ValueError) as cm:
            L.resolve_layout({}, {"layout": {"fontsize": "11"}})
        self.assertIn("allowed options", str(cm.exception))
        with self.assertRaises(ValueError):
            L.resolve_layout({}, {"layout": "paper: a4"})
        with self.assertRaises(ValueError):
            L.resolve_layout({}, {"layout": {"paper": ["a4", "letter"]}})

    def test_precedence_doctype_then_config(self):
        dt = {"layout": {"paper": "letter", "font_size": 10}}
        self.assertEqual(L.resolve_layout(dt, {}), {"paper": "letter", "font_size": "10"})
        self.assertEqual(L.resolve_layout(dt, {"layout": {"paper": "a4"}}), {"paper": "a4", "font_size": "10"})

    def test_citation_style_whitelist_and_precedence(self):
        for s in L.CITATION_STYLES:
            self.assertEqual(L.resolve_citation_style({}, {"citation_style": s}), s)
        self.assertEqual(L.resolve_citation_style({"citation_style": "apa7"}, {}), "apa7")
        self.assertEqual(L.resolve_citation_style({"citation_style": "apa7"}, {"citation_style": "vancouver"}), "vancouver")
        with self.assertRaises(ValueError) as cm:
            L.resolve_citation_style({}, {"citation_style": "apa"})
        self.assertIn("apa7", str(cm.exception))

    def test_check_config_collects_all_errors(self):
        errs = L.check_config({}, {"citation_style": "nope", "layout": {"paper": "a5", "colour": "pink"}})
        self.assertEqual(len([e for e in errs if "layout.paper" in e or "colour" in e or "citation_style" in e]) >= 2, True)

    def test_columns_two_needs_article_class(self):
        errs = L.check_config({"latex_defaults": "templates/latex/book.yaml"}, {"layout": {"columns": 2}}, skill_dir=H.ROOT)
        self.assertTrue(any("article-based" in e for e in errs), errs)
        self.assertEqual(L.check_config({}, {"layout": {"columns": 2}}, skill_dir=H.ROOT), [])

    def test_custom_template_rejects_layout_unless_declared(self):
        ieee = C.load_yaml(os.path.join(H.DOCTYPES, "ieee-report.yaml"))
        self.assertTrue(L.check_config(ieee, {"layout": {"paper": "letter"}}, skill_dir=H.ROOT))
        declared = dict(ieee, layout_options=["paper"])
        self.assertEqual(L.check_config(declared, {"layout": {"paper": "letter"}}, skill_dir=H.ROOT), [])
        self.assertTrue(L.check_config(declared, {"layout": {"margins": "1in"}}, skill_dir=H.ROOT))

    def test_csl_needs_template_support(self):
        ieee = C.load_yaml(os.path.join(H.DOCTYPES, "ieee-report.yaml"))
        errs = L.check_config(ieee, {"citation_style": "apa7"}, skill_dir=H.ROOT)
        self.assertTrue(any("csl-refs" in e for e in errs), errs)
        self.assertEqual(L.check_config(ieee, {"citation_style": "ieee"}, skill_dir=H.ROOT), [])

    def test_default_plan_is_empty(self):
        d = tempfile.mkdtemp(prefix="ms_plan_")
        try:
            plan = L.build_plan({"latex_defaults": "templates/latex/article.yaml", "citation_style": "numeric"}, {}, H.ROOT, d)
            self.assertEqual(plan.args, [])
            self.assertEqual(plan.pre_args, [])
            self.assertEqual(plan.files, {})
            self.assertFalse(plan.citeproc)
            self.assertTrue(plan.defaults.endswith("templates/latex/article.yaml"))
            self.assertEqual(os.listdir(d), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_header_file_contains_only_whitelisted_text(self):
        text = L._header_text({"header": "title-author", "page_numbers": "top-right", "font": "times",
                               "table_style": "plain", "caption_position": "top"})
        self.assertIn("\\fancyhead[R]{\\thepage}", text)
        self.assertNotIn("\\input", text)

    def test_every_csl_file_vendored_and_listed(self):
        notice = C.read_text(os.path.join(H.ROOT, "templates", "csl", "NOTICE.md"))
        for name, spec in L.CITATION_STYLES.items():
            if spec["engine"] == "csl":
                p = os.path.join(H.ROOT, "templates", "csl", spec["csl"])
                self.assertTrue(os.path.isfile(p), name)
                self.assertIn(spec["csl"], notice)
                self.assertNotIn("independent-parent", C.read_text(p))

    def test_describe_lists_everything(self):
        text = L.describe()
        for k in list(L.LAYOUT_KEYS) + list(L.CITATION_STYLES):
            self.assertIn(k, text)


class ConfigCommands(unittest.TestCase):
    def test_layouts_and_check_config_cli(self):
        root = tempfile.mkdtemp(prefix="ms_cli_")
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = H.run_script("ms_state.py", "layouts", cwd=root)
        self.assertEqual(rc, 0)
        self.assertIn("vancouver", out)
        self.assertIn("helvetica-sans", out)
        H.run_script("ms_state.py", "init", "demo", "--doctype", "research-report", cwd=root)
        self.assertEqual(H.run_script("ms_state.py", "check-config", cwd=root)[0], 0)
        with open(os.path.join(root, "manuscript", "demo", ".ms", "project-config.yaml"), "a") as f:
            f.write("citation_style: apa\nlayout:\n  paper: a5\n  margins: 1in}x\n")
        rc, out = H.run_script("ms_state.py", "check-config", cwd=root)
        self.assertEqual(rc, 1)
        self.assertEqual(out.count("ERROR"), 3, out)  # all problems at once
        self.assertIn("allowed values: a4, letter", out)

    def test_validate_markdown_accepts_new_styles_and_flags_typos(self):
        for style, expect_err in (("apa7", False), ("vancouver", False), ("chicago-notes", False), ("apa", True)):
            root, d = H.approved_project("citation_style: %s" % style, approve=False)
            self.addCleanup(shutil.rmtree, root, True)
            rc, out = H.run_script("validate_markdown.py", "--json", cwd=root)
            res = json.loads(out)
            codes = [e["code"] for e in res["errors"]]
            self.assertEqual("invalid-config" in codes, expect_err, (style, codes))


@NEED_PANDOC
class GeneratedLatex(unittest.TestCase):
    def gen(self, cfg, doctype="research-report", late=False):
        root, d, rc, out, tex = generate("", doctype, config_after=cfg) if late else generate(cfg, doctype)
        self.addCleanup(shutil.rmtree, root, True)
        return rc, out, C.read_text(tex) if os.path.isfile(tex) else "", d

    def test_options_land_in_tex(self):
        rc, out, tex, d = self.gen("layout:\n  paper: letter\n  font_size: 12\n  spacing: double\n  margins: 1in\n"
                                   "  columns: 2\n  colour: print\n  heading_numbering: off")
        self.assertEqual(rc, 0, out)
        self.assertIn("letterpaper", tex)
        self.assertNotIn("a4paper", tex)
        self.assertEqual(len(re.findall(r"\b1[012]pt\b", tex.split("\\begin{document}")[0])), 1)
        self.assertIn("12pt", tex)
        self.assertIn("twocolumn", tex)
        self.assertIn("\\setstretch{2}", tex)
        self.assertIn("margin=1in", tex)
        self.assertIn("hidelinks", tex)
        self.assertIn("secnumdepth}{-\\maxdimen}", tex)

    def test_header_font_table_caption_in_tex(self):
        rc, out, tex, d = self.gen("layout:\n  header: title-author\n  page_numbers: bottom-right\n  font: times\n"
                                   "  table_style: plain\n  caption_position: top")
        self.assertEqual(rc, 0, out)
        for needle in ("\\usepackage{fancyhdr}", "\\fancyfoot[R]{\\thepage}", "\\fancyhead[C]{\\msruntitle}",
                       "texgyretermes", "\\renewcommand{\\toprule}{\\hline}", "capposition=top"):
            self.assertIn(needle, tex)
        self.assertIn("layout-header.tex", C.read_text(os.path.join(d, ".ms", "logs", "latex-generation.log")))

    def test_two_columns_uses_single_column_tables(self):
        rc, out, tex, d = self.gen("layout:\n  columns: 2")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("longtable}", tex.split("\\begin{document}")[1])
        self.assertIn("\\begin{tabular}", tex)

    def test_doctype_layout_default_overridden_by_config(self):
        d = tempfile.mkdtemp(prefix="ms_plan_")
        self.addCleanup(shutil.rmtree, d, True)
        dt = {"latex_defaults": "templates/latex/article.yaml", "layout": {"paper": "letter", "font_size": 10}}
        plan = L.build_plan(dt, {"layout": {"font_size": 12}}, H.ROOT, d)
        merged = json.loads(C.read_text(plan.defaults))
        self.assertIn("letterpaper", merged["variables"]["classoption"])
        self.assertIn("12pt", merged["variables"]["classoption"])
        self.assertNotIn("10pt", merged["variables"]["classoption"])
        self.assertNotIn("11pt", merged["variables"]["classoption"])

    def test_invalid_values_rejected_before_pandoc(self):
        for cfg, needle in (("layout:\n  paper: a5", "allowed values: a4, letter"),
                            ("layout:\n  margins: 1in}\\x", "layout.margins"),
                            ("layout:\n  columns: 3", "allowed values: 1, 2"),
                            ("layout:\n  bogus: 1", "unknown layout option"),
                            ("citation_style: harvard-ish", "allowed values")):
            rc, out, tex, d = self.gen(cfg, late=True)
            self.assertEqual(rc, 2, cfg)
            self.assertIn(needle, out)
            self.assertEqual(tex, "")

    def test_ieee_doctype_rejects_layout_and_csl(self):
        rc, out, tex, d = self.gen("layout:\n  paper: letter", "ieee-report")
        self.assertEqual(rc, 2)
        self.assertIn("not supported with this custom pandoc template", out)
        rc, out, tex, d = self.gen("citation_style: apa7", "ieee-report")
        self.assertEqual(rc, 2)
        self.assertIn("csl-refs", out)

    def test_thesis_rejects_two_columns(self):
        rc, out, tex, d = self.gen("layout:\n  columns: 2", "thesis")
        self.assertEqual(rc, 2)
        self.assertIn("article-based", out)

    def test_citeproc_tex_shape_and_state_record(self):
        rc, out, tex, d = self.gen("citation_style: apa7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(tex.count("\\begin{CSLReferences}"), 1)  # bibliography exactly once
        self.assertNotIn("\\bibliography{", tex)
        self.assertNotIn("\\citep{", tex)
        self.assertIn("\\citeproc{ref-smith2020}", tex)
        self.assertEqual(len(re.findall(r"\\section\*?\{References\}", tex)), 1)
        self.assertNotIn("key: smith2020", tex)  # review list never leaks
        st = C.read_json(os.path.join(d, ".ms", "state.json"))
        inp = st["latex"]["inputs"]
        self.assertEqual(inp["citation_style"], "apa7")
        self.assertEqual(inp["csl"]["sha256"], C.sha256_file(os.path.join(H.ROOT, "templates", "csl", "apa.csl")))
        self.assertIn("pandoc-defaults.yaml", inp["files"])

    def test_state_detects_changed_latex_inputs(self):
        rc, out, tex, d = self.gen("layout:\n  header: running-title")
        self.assertEqual(rc, 0, out)
        root = os.path.dirname(os.path.dirname(d))
        st = S.load(root, "demo")
        self.assertIn("layout-header.tex", st["latex"]["inputs"]["files"])
        self.assertFalse([c for c in S.verify(root, "demo", st) if c["artifact"] == "latex"])
        with open(os.path.join(d, ".ms", "latex", "layout-header.tex"), "a") as f:
            f.write("% tampered\n")
        ch = [c for c in S.verify(root, "demo", st) if c["artifact"] == "latex"]
        self.assertEqual([c["kind"] for c in ch], ["latex_input_changed"])

    def test_default_run_records_empty_inputs_and_no_generated_files(self):
        rc, out, tex, d = self.gen("")
        self.assertEqual(rc, 0, out)
        latex_dir = os.path.join(d, ".ms", "latex")
        self.assertFalse(os.path.exists(os.path.join(latex_dir, "pandoc-defaults.yaml")))
        self.assertFalse(os.path.exists(os.path.join(latex_dir, "layout-header.tex")))
        st = C.read_json(os.path.join(d, ".ms", "state.json"))
        self.assertEqual(st["latex"]["inputs"]["files"], {})
        self.assertNotIn("csl", st["latex"]["inputs"])

    def test_preview_uses_same_assembly(self):
        root, d = H.approved_project("citation_style: vancouver\nlayout:\n  header: running-title", approve=False)
        self.addCleanup(shutil.rmtree, root, True)
        rc, out = H.run_script("md_to_latex.py", "--preview", cwd=root)
        self.assertEqual(rc, 0, out)
        tex = C.read_text(os.path.join(d, ".ms", "latex", "demo-preview.tex"))
        self.assertIn("DRAFT PREVIEW -- NOT APPROVED", tex)
        self.assertIn("\\begin{CSLReferences}", tex)
        self.assertIn("\\msruntitle", tex)
        self.assertLess(tex.index("\\msruntitle"), tex.index("DRAFT PREVIEW -- NOT APPROVED"))  # marker comes last and wins
        st = S.load(root, "demo")
        self.assertEqual(st["latex"]["path"], None)  # preview never touches state

    def test_prepare_markdown_citeproc_cases(self):
        import md_to_latex as M
        t, _ = M.prepare_markdown("# A\n\ntext\n\n# References\n", citeproc=True)
        self.assertEqual(t.count("{#refs}"), 1)
        self.assertIn("# References {-}", t)
        t, _ = M.prepare_markdown("# A\n\ntext\n\n# References\n\n<!-- references:start -->\n- x\n<!-- references:end -->\n\n# Appendix\n\nz\n", citeproc=True)
        self.assertEqual(t.count("{#refs}"), 1)
        self.assertNotIn("- x", t)
        self.assertLess(t.index("{#refs}"), t.index("# Appendix"))
        t, _ = M.prepare_markdown("# A\n\ntext [@k]\n", citeproc=True)  # no references section: one is appended
        self.assertIn("# References {-}", t)
        user = "# A\n\n# References\n\n::: {#refs}\n:::\n"
        self.assertEqual(M.prepare_markdown(user, citeproc=True)[0], user)  # user's own placeholder respected
        # BibTeX path unchanged
        t, _ = M.prepare_markdown("# A\n\ntext\n\n# References\n", citeproc=False)
        self.assertNotIn("References", t)


@NEED_PDF
class LayoutCompiles(unittest.TestCase):
    """Every whitelisted layout value compiles under tectonic (compile-or-don't-ship)."""

    def compiled(self, cfg, doctype="research-report"):
        root, d, rc, out, tex = generate(cfg, doctype)
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(H.run_script("validate_latex.py", tex, cwd=root)[0], 0)
        rc, out = compile_tex(tex)
        self.assertEqual(rc, 0, "%s\n%s" % (cfg, out))
        return pdf_text(tex[:-4] + ".pdf"), tex

    def test_each_option_value_compiles(self):
        for key, vals in L.LAYOUT_KEYS.items():
            for v in (vals or ("2.5cm", "25mm", "1in")):
                with self.subTest(option=key, value=v):
                    text, _ = self.compiled("layout:\n  %s: %s" % (key, v))
                    self.assertIn("Fixture Report", text)

    def test_combined_layout_on_each_doctype_class(self):
        cfg = ("layout:\n  paper: letter\n  font_size: 12\n  spacing: onehalf\n  margins: 2cm\n  font: libertinus\n"
               "  header: title-author\n  page_numbers: top-right\n  table_style: plain\n  caption_position: top")
        text, _ = self.compiled(cfg)
        self.assertIn("Test Author", text)
        text, _ = self.compiled(cfg, "thesis")  # report class: chapter pages follow the settings
        self.assertIn("Chapter 1", text)

    def test_page_size_and_columns_effects(self):
        _, tex = self.compiled("layout:\n  paper: letter")
        info = subprocess.run(["pdfinfo", tex[:-4] + ".pdf"], capture_output=True, text=True).stdout
        self.assertIn("letter", info)
        _, tex = self.compiled("layout:\n  paper: a4")
        info = subprocess.run(["pdfinfo", tex[:-4] + ".pdf"], capture_output=True, text=True).stdout
        self.assertIn("A4", info)

    def test_fonts_actually_applied(self):
        expect = {"times": "TeXGyreTermes", "palatino": "TeXGyrePagella", "libertinus": "LibertinusSerif",
                  "helvetica-sans": "TeXGyreHeros"}
        for font, face in expect.items():
            with self.subTest(font=font):
                _, tex = self.compiled("layout:\n  font: %s" % font)
                fonts = subprocess.run(["pdffonts", tex[:-4] + ".pdf"], capture_output=True, text=True).stdout
                self.assertIn(face, fonts)

    def test_header_text_in_pdf(self):
        text, _ = self.compiled("layout:\n  header: running-title\n  page_numbers: bottom-right")
        self.assertGreaterEqual(text.count("A Fixture Report"), 2)  # title block + running header


if __name__ == "__main__":
    unittest.main()
