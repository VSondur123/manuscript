import os
import unittest

import helpers as H
import ms_common as C
from validate_markdown import validate


class MarkdownValidation(unittest.TestCase):
    def setUp(self):
        self.d = H.copy_valid_project()
        self.draft = os.path.join(self.d, "draft.md")
        self.bib = os.path.join(self.d, "refs.bib")
        self.plan = os.path.join(self.d, "plan.md")
        self.dt = C.load_yaml(os.path.join(H.DOCTYPES, "research-report.yaml"))

    def run_v(self, **kw):
        return validate(self.draft, self.bib, self.plan, self.dt, kw.get("config"))

    def write(self, text):
        with open(self.draft, "w") as f:
            f.write(text)

    def edit(self, old, new):
        t = C.read_text(self.draft)
        self.assertIn(old, t)
        self.write(t.replace(old, new))

    def test_valid_fixture_has_no_errors(self):
        res = self.run_v()
        self.assertEqual(res["errors"], [], res["errors"])
        self.assertEqual(res["warnings"], [], res["warnings"])

    def test_heading_skip(self):
        self.edit("# Methodology\n", "# Methodology\n\n### Deep\n\ntext\n")
        self.assertIn("heading-skip", H.codes(self.run_v(), "errors"))

    def test_empty_section(self):
        self.edit("# Results\n", "# Results\n\n# Empty One\n")
        self.assertIn("empty-section", H.codes(self.run_v(), "errors"))

    def test_missing_required_section(self):
        self.edit("# Conclusion\n\nThe work is complete [@lee2018].\n", "")
        self.assertIn("missing-required-section", H.codes(self.run_v(), "errors"))

    def test_missing_reference_in_bibliography(self):  # fixture 6: missing reference
        self.edit("[@smith2020]", "[@smith2020; @ghost1999]")
        res = self.run_v()
        self.assertIn("missing-bib-entry", H.codes(res, "errors"))
        self.assertTrue(any("ghost1999" in i["message"] for i in res["errors"]))

    def test_unused_bib_entry_warns(self):
        self.edit("[@smith2020] ", "")
        self.assertIn("unused-bib-entry", H.codes(self.run_v(), "warnings"))

    def test_missing_figure_file(self):  # fixture 13
        os.remove(os.path.join(self.d, "figures", "arch.png"))
        self.assertIn("figure-missing-file", H.codes(self.run_v(), "errors"))

    def test_figure_without_caption(self):
        self.edit("![System architecture]", "![]")
        self.assertIn("figure-no-caption", H.codes(self.run_v(), "errors"))

    def test_broken_internal_link(self):
        self.edit("(#fig-arch)", "(#fig-nope)")
        self.assertIn("broken-link", H.codes(self.run_v(), "errors"))

    def test_unreferenced_figure_warns(self):
        self.edit("See [Figure](#fig-arch) and ", "See ")
        self.assertIn("figure-unreferenced", H.codes(self.run_v(), "warnings"))

    def test_table_without_caption(self):
        self.edit("Table: Results summary {#tbl-res}\n", "")
        self.assertIn("table-no-caption", H.codes(self.run_v(), "errors"))

    def test_placeholder_blocks(self):  # fixture 8: unsupported claim flagged
        self.edit("The work is complete", "[[UNSUPPORTED: accuracy was 99%]] The work is complete")
        self.assertIn("unresolved-placeholder", H.codes(self.run_v(), "errors"))

    def test_placeholder_in_code_block_ignored(self):
        self.edit("# Conclusion\n", "# Conclusion\n\n```\nTODO in code\n```\n")
        self.assertNotIn("unresolved-placeholder", H.codes(self.run_v(), "errors"))

    def test_word_limit(self):
        res = self.run_v(config={"limits": {"max_words": 10}})
        self.assertIn("over-word-limit", H.codes(res, "errors"))

    def test_plan_section_missing_and_order(self):  # fixture 4: TOC consistency
        self.edit("# Methodology", "# Approach")
        res = self.run_v()
        self.assertIn("plan-section-missing", H.codes(res, "warnings"))
        self.assertIn("section-not-in-plan", H.codes(res, "warnings"))

    def test_section_order_needs_confirmation(self):
        t = C.read_text(self.draft)
        a, b = t.index("# Methodology"), t.index("# Results")
        c = t.index("# Conclusion")
        self.write(t[:a] + t[b:c] + t[a:b] + t[c:])
        self.assertIn("section-order-differs", H.codes(self.run_v(), "confirmations"))

    def test_config_overrides_required_sections(self):
        self.edit("# Methodology", "# Approach")
        res = validate(self.draft, self.bib, self.plan, self.dt, {"required_sections": ["Introduction", "Approach"]})
        self.assertNotIn("missing-required-section", H.codes(res, "errors"))
        res = validate(self.draft, self.bib, self.plan, self.dt, None)
        self.assertIn("missing-required-section", H.codes(res, "errors"))

    def test_no_abstract(self):
        self.edit('abstract: |\n  This is a test abstract.\n', "")
        self.assertIn("no-abstract", H.codes(self.run_v(), "errors"))


if __name__ == "__main__":
    unittest.main()
