import unittest

import helpers as H  # noqa: F401
from style_scan import scan

UNIFORM = " ".join(["The system delves into the multifaceted landscape of data processing today."] * 20)


class StyleScan(unittest.TestCase):
    def test_flags_uniform_template_prose(self):
        r = scan(UNIFORM)
        self.assertIn("delves", r["tell_words"])
        self.assertLess(r["sentence_length"]["cv"], 0.1)
        self.assertTrue(r["findings"])

    def test_ignores_code_math_citations(self):
        r = scan("```\ndelve delve delve delve delve delve delve delve\n```\n\nWe measured latency across five runs [@smith2020] and report the median value here.")
        self.assertEqual(r["tell_words"], {})

    def test_varied_prose_is_cleaner(self):
        text = ("We ran it twice. The first run failed because the cache was cold, and the second, after a warm-up of "
                "ten minutes on the same host, finished in 41 seconds. That gap matters. Latency, not throughput, "
                "dominated every trial we looked at, which surprised us given earlier reports.")
        r = scan(text)
        self.assertEqual(r["tell_words"], {})
        self.assertGreater(r["sentence_length"]["cv"], 0.45)

    def test_technical_terms_get_soft_wording_and_density_gets_strong_wording(self):
        prose = ("We fit a robust regression to the data and plot the fitness landscape. The vital signs were logged every minute by the nurse "
                 "on duty, and a comprehensive bootstrap resampled the residuals one thousand times. " * 1 +
                 " ".join("Each additional run on the cluster took roughly forty minutes of wall time, so we capped the sweep at nine." for _ in range(150)))
        r = scan(prose)
        self.assertTrue(r["tell_words"])
        msg = " ".join(r["findings"])
        self.assertIn("second look", msg)
        self.assertIn("source terminology", msg)
        self.assertNotIn("Replace with plain", msg)
        self.assertNotIn("DENSE", msg)
        dense = " ".join(["The robust holistic approach leverages a comprehensive and crucial framework today."] * 10)
        self.assertIn("DENSE", " ".join(scan(dense)["findings"]))
        self.assertNotIn("Replace with plain", " ".join(scan(dense)["findings"]))


if __name__ == "__main__":
    unittest.main()
