# Raw verification artifact parsing

Codex owns this package and `tests/artifacts/` while Claude owns the ecosystem adapters.
This is a CP1 parsing component, not a completed sandbox artifact transport.

`parse_junit(xml_bytes)` derives `SuiteCounts` from individual testcase records,
checks summary counters, handles nested suites without double counting, and rejects
duplicates, ambiguous outcomes, unsafe XML declarations and oversized artifacts.
Skips and errors remain separate from passing tests; an empty suite stays empty.

`parse_django_probe(stdout_bytes, exit_code=..., expected_cve=...,
expected_version=..., expected_sha256=...)` parses the existing owned probe's output.
The controller must supply expectations from the frozen probe and selected runtime.
Nonzero process exits, malformed output, changed probe hashes, mismatched runtimes,
failed HTTP requests and boolean-like strings cannot establish remediation.

## Integration boundary

These functions establish internal consistency only. They cannot authenticate
files or certify execution. They do not set `artifacts_verified` or return a green
`VerifyReport`. Extra model-written trust fields have no effect.

Before marking a report as verified, a separate trusted runner/transport must:

1. Obtain actual process outputs and exit codes independently of model prose.
2. Bind them to the sandbox/environment, immutable source commit and exact patch.
3. Verify the frozen tests and probe were executed unchanged with the required commands.
4. Record actual installed dependencies, install/check results and process timeouts.
5. Preserve the raw artifacts under `runs/` and apply the existing before/after gate.

Parsing local files is still local inspection. Passing unit tests and the owned
fixture must never be presented as a verified target migration or cloud benchmark.

## Local verification

```sh
uv run pytest -q tests/artifacts/
```

JUnit producers without individual testcase records, or with unsupported retry or
suite-level error records, are rejected conservatively. A runner should preserve
those raw outputs and report unsupported evidence instead of inventing passes.

The local full controller suite exposed another unsupported export: pytest's
passing unittest subtests contribute to the suite counter but have no individual
testcase records in its JUnit file. Such reports are deliberately rejected. The
transport must use a complete exporter; silently subtracting subtests would hide
missing evidence. Focused parser tests emit complete JUnit and are parsed directly.
