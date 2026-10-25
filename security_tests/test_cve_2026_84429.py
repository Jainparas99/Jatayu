"""CVE-2026-84429: quadratic-time header parameter parsing. [CP1: write and prove on 4.2 vs 5.2]

Sketch: build a large crafted header value, time
django.utils.http.parse_header_parameters (or a request through the test client),
and assert it finishes under a threshold. Calibrate the size so 4.2.30 clearly exceeds it
and 5.2.18 clearly doesn't. Record both timings as evidence.
"""

import unittest


@unittest.skip("CP1: not written yet")
class CVE202684429(unittest.TestCase):
    def test_header_parsing_is_not_quadratic(self):
        raise NotImplementedError
