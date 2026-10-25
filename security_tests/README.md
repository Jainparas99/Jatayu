# Independent security probes

`probe_formset.py` is a standalone owned application fixture using SQLite in memory and Django's HTTP test client. Run it in separate pinned environments. It exercises the editable-primary-key formset boundary and a benign edit without network requests. `test_cve_2026_87975.py` asserts the protected result and intentionally fails under the vulnerable old version.

The same fixture was locally vulnerable under 4.2.30 and blocked under 5.2.18, with a passing benign control on both. Use `jatayu prove-fixture OLD_PYTHON NEW_PYTHON` to reproduce and save raw output/hash provenance. This establishes the fixture behavior only.

These files are not automatically copied into arbitrary targets. A target-specific adapter must prove the target exposes the same feature and must preserve probes outside the migration agent's control. The header timing test remains a deferred skipped placeholder and cannot count toward verification. Cloud artifact verification remains pending.
