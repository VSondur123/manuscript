import json
import os
import shutil
import tempfile
import unittest

import helpers as H
import ms_common as C
import ms_state as S
import validate_markdown as VM


class StateWorkflow(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ms_state_")
        S.init_project(self.root, "doc", "research-report", "T")
        self.d = S.pdir(self.root, "doc")
        H.install_fixture(self.d, "doc")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def st(self):
        return S.load(self.root, "doc")

    def go(self, stage):
        st = self.st()
        S.set_stage(self.root, "doc", st, stage)
        S.save(self.root, "doc", st)

    def to_plan_pending(self):
        for s in ("DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL"):
            self.go(s)

    def to_md_pending(self):
        self.to_plan_pending()
        st = self.st()
        S.approve(self.root, "doc", st, "plan", "APPROVE PLAN")
        S.save(self.root, "doc", st)
        for s in ("EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"):
            self.go(s)

    def validate_draft(self):
        self.assertEqual(VM.main(["--project", "doc", "--root", self.root]), 0)

    def test_cannot_skip_stages(self):
        with self.assertRaises(S.StateError):
            self.go("PLAN_PENDING_APPROVAL")

    def test_plan_approval_requires_exact_phrase(self):
        self.to_plan_pending()
        st = self.st()
        for bad in ("looks good", "approve plan", "APPROVE MARKDOWN"):
            with self.assertRaises(S.StateError):
                S.approve(self.root, "doc", st, "plan", bad)
        self.assertEqual(self.st()["stage"], "PLAN_PENDING_APPROVAL")

    def test_cannot_enter_plan_approved_directly(self):
        self.to_plan_pending()
        with self.assertRaises(S.StateError):
            self.go("PLAN_APPROVED")

    def test_markdown_rejection_phrase(self):  # fixture 10
        self.to_md_pending()
        self.validate_draft()
        st = self.st()
        with self.assertRaises(S.StateError):
            S.approve(self.root, "doc", st, "markdown", "looks good")
        self.assertEqual(self.st()["stage"], "MARKDOWN_PENDING_APPROVAL")
        self.assertIsNone(self.st()["markdown_approval"])

    def test_approval_requires_clean_validation(self):
        self.to_md_pending()
        st = self.st()
        with self.assertRaises(S.StateError):  # never validated
            S.approve(self.root, "doc", st, "markdown", "APPROVE MARKDOWN")
        with open(os.path.join(self.d, "doc-report.md"), "a") as f:
            f.write("\nTODO finish\n")
        self.assertEqual(VM.main(["--project", "doc", "--root", self.root]), 1)
        with self.assertRaises(S.StateError):
            S.approve(self.root, "doc", self.st(), "markdown", "APPROVE MARKDOWN")

    def test_approve_snapshot_and_latex_gate(self):  # fixture 11
        self.to_md_pending()
        with self.assertRaises(S.StateError):  # LATEX_GENERATION unreachable before approval
            self.go("LATEX_GENERATION")
        self.validate_draft()
        st = self.st()
        S.approve(self.root, "doc", st, "markdown", "APPROVE MARKDOWN")
        S.save(self.root, "doc", st)
        st = self.st()
        snap = os.path.join(self.d, st["markdown_approval"]["snapshot"])
        self.assertTrue(os.path.isfile(snap))
        self.assertEqual(C.sha256_file(snap), st["markdown_approval"]["sha256"])
        self.assertEqual(st["stage"], "MARKDOWN_APPROVED")
        self.go("LATEX_GENERATION")

    def test_edit_after_approval_invalidates(self):
        self.to_md_pending()
        self.validate_draft()
        st = self.st()
        S.approve(self.root, "doc", st, "markdown", "APPROVE MARKDOWN")
        S.save(self.root, "doc", st)
        with open(os.path.join(self.d, "doc-report.md"), "a") as f:
            f.write("\nExtra sentence.\n")
        st = self.st()
        kinds = [c["kind"] for c in S.verify(self.root, "doc", st)]
        self.assertIn("approval_stale", kinds)
        self.assertEqual(S.markdown_approval_status(self.root, "doc", st), "stale")
        with self.assertRaises(S.StateError):
            S.set_stage(self.root, "doc", st, "LATEX_GENERATION")
        self.assertEqual(S.main(["--root", self.root, "verify", "doc", "--fix"]), 3)
        self.assertEqual(self.st()["stage"], "MARKDOWN_PENDING_APPROVAL")

    def test_tampered_snapshot_detected(self):
        self.to_md_pending()
        self.validate_draft()
        st = self.st()
        S.approve(self.root, "doc", st, "markdown", "APPROVE MARKDOWN")
        S.save(self.root, "doc", st)
        snap = os.path.join(self.d, self.st()["markdown_approval"]["snapshot"])
        os.chmod(snap, 0o644)
        with open(snap, "a") as f:
            f.write("tamper")
        self.assertTrue(any(c["artifact"] == "approved" for c in S.verify(self.root, "doc")))

    def test_external_modification_and_sync(self):  # fixture 17
        st = self.st()
        S.sync(self.root, "doc", st)
        S.save(self.root, "doc", st)
        self.assertEqual(S.verify(self.root, "doc"), [])
        with open(os.path.join(self.d, "plan.md"), "a") as f:
            f.write("- Extra\n")
        ch = S.verify(self.root, "doc")
        self.assertEqual([(c["artifact"], c["kind"]) for c in ch], [("plan", "modified_externally")])
        st = self.st()
        v0 = st["artifacts"]["plan"]["version"]
        S.sync(self.root, "doc", st)
        self.assertEqual(st["artifacts"]["plan"]["version"], v0 + 1)

    def test_resume_new_session_and_second_project(self):  # fixtures 16, 18
        self.to_plan_pending()
        S.init_project(self.root, "other", "technical-report")
        self.assertEqual(S.list_projects(self.root), ["doc", "other"])
        with self.assertRaises(S.StateError):
            S.resolve(self.root, None)  # ambiguous
        self.assertEqual(S.load(self.root, "other")["stage"], "INITIALISED")
        self.assertEqual(S.load(self.root, "doc")["stage"], "PLAN_PENDING_APPROVAL")
        self.assertEqual(S.summary(self.root, "doc", S.load(self.root, "doc"), [])["pending_approvals"], ["plan (say: APPROVE PLAN)"])

    def test_backup_preserves_previous_version(self):
        rel = S.backup(self.root, "doc", "doc-report.md")
        self.assertTrue(rel.startswith(".ms/history"))
        self.assertEqual(C.read_text(os.path.join(self.d, rel)), C.read_text(os.path.join(self.d, "doc-report.md")))

    def test_rework_clears_completed(self):
        self.to_md_pending()
        self.go("MARKDOWN_DRAFTING")
        self.assertNotIn("MARKDOWN_VALIDATION", self.st()["completed_stages"])


class YamlSubset(unittest.TestCase):
    def test_parse(self):
        y = C.parse_yaml("a: 1\nb:\n  - x\n  - 'y z'\nc:\n  d: true # c\n  e: [1, 2]\nf: null\n")
        self.assertEqual(y, {"a": 1, "b": ["x", "y z"], "c": {"d": True, "e": [1, 2]}, "f": None})


if __name__ == "__main__":
    unittest.main()
