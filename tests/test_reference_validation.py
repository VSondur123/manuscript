import unittest

import helpers  # noqa: F401
from validate_references import cited_keys, check, parse_bib

BIB = """
@article{a1, author={X, Y}, title={T}, journal={J}, year={2020}, doi={10.1000/abc}}
@article{a1, author={X, Y}, title={T}, journal={J}, year={2020}}
@article{bad, author={Unknown}, title={T}, year={20x0}}
@book{b1, author={Q}, title={B}, year={2001}}
"""


class RefValidation(unittest.TestCase):
    def test_parse_and_duplicates(self):
        entries, dups = parse_bib(BIB)
        self.assertEqual(set(entries), {"a1", "bad", "b1"})
        self.assertEqual([k for k, _ in dups], ["a1"])

    def test_checks(self):
        e, d = parse_bib(BIB)
        errs, warns = check(e, d)
        codes = [c for _, c, _ in errs]
        self.assertIn("duplicate-key", codes)
        self.assertIn("missing-field", codes)   # bad lacks journal, b1 lacks publisher
        self.assertIn("suspect-value", codes)   # author = Unknown
        self.assertIn("odd-year", [c for _, c, _ in warns])

    def test_cited_keys(self):
        self.assertEqual(cited_keys("see [@a1; @b1, p. 3] and `[@code]`\n\\citep{x,y}"), {"a1", "b1", "x", "y"})


if __name__ == "__main__":
    unittest.main()
