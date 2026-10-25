import unittest
from dataclasses import replace

from unpinned.evidence import RunEvidence, review_blockers


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.before = RunEvidence(12, 12, 0, True, True, "vulnerable", "a" * 64)
        self.after = replace(self.before, probe="blocked")

    def test_complete_evidence_is_ready_for_review(self):
        self.assertEqual(review_blockers(self.before, self.after), [])

    def test_inconclusive_probe_is_never_remediation(self):
        for outcome in ("error", "timeout", "skipped", "vulnerable"):
            with self.subTest(outcome=outcome):
                self.assertTrue(review_blockers(self.before, replace(self.after, probe=outcome)))

    def test_no_baseline_reproduction_blocks_claim(self):
        self.assertTrue(review_blockers(replace(self.before, probe="blocked"), self.after))

    def test_empty_or_incomplete_suite_blocks_review(self):
        for changes in (
            {"tests_collected": 0, "tests_passed": 0},
            {"tests_passed": 11},
            {"tests_exit_code": 1},
            {"checks_passed": False},
            {"benign_control_passed": False},
        ):
            for side in ("before", "after"):
                with self.subTest(changes=changes, side=side):
                    before = replace(self.before, **changes) if side == "before" else self.before
                    after = replace(self.after, **changes) if side == "after" else self.after
                    self.assertTrue(review_blockers(before, after))

    def test_changed_or_missing_probe_blocks_review(self):
        for digest in ("", "b" * 64, "invalid"):
            self.assertTrue(review_blockers(self.before, replace(self.after, probe_sha256=digest)))


if __name__ == "__main__":
    unittest.main()
