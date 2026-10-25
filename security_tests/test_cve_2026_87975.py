"""CVE-2026-87975: formset with editable PKs; a forged POST acts outside the queryset. [CP1]

Sketch: define a minimal model with a natural/UUID primary key in a test-only app (or use an
existing model of the target project), build a modelformset over a restricted queryset, POST a
forged form that deletes/creates an object outside it, and assert the object is untouched.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path


class CVE202687975(unittest.TestCase):
    def test_forged_formset_cannot_touch_rows_outside_queryset(self):
        process = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("probe_formset.py"))],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        result = json.loads(process.stdout)
        self.assertTrue(result["benign_control_passed"], process.stdout)
        self.assertEqual(result["outcome"], "blocked", process.stdout)
