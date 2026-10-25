# ruff: noqa: E501  (embedded shell script and fixed-format strings)
"""Controller-owned verification harness for the Antigravity sandbox.

The model in the sandbox only *runs* a script we wrote. The script, the patch archive and
the exact versions are mounted into the environment as inline sources. Afterwards the
controller downloads the raw files the script produced (JUnit XML, logs, exit codes, probe
stdout) through the Environments Files API and builds the VerifyReport from those bytes
alone. The model's chat reply is never parsed for results.

Integrity checks before `artifacts_verified=True`:
- the harness and patch archive we download back hash to what we uploaded;
- the checked-out commit is the immutable source commit;
- the installed framework version is the exact version requested;
- the security probe file in the sandbox hashes to the frozen SHA-256;
- the script reached its DONE marker.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from ..artifacts.parse import ArtifactError, parse_django_probe, parse_junit
from ..models import ExploitResult, Failure, SuiteCounts, VerifyReport
from ..parse import Patch, check_path

HARNESS_DIR = "jatayu"  # where sources are mounted, relative to the workspace root
OUT_DIR = f"{HARNESS_DIR}/out"
ARTIFACTS = [
    "DONE",
    "head.txt",
    "python.txt",
    "django.txt",
    "install.exit",
    "install.log",
    "tests.exit",
    "tests.stdout",
    "tests.stderr",
    "junit.xml",
    "check.exit",
    "check.stdout",
    "check.stderr",
    "probe.sha256",
    "probe.exit",
    "probe.stdout",
    "probe.stderr",
]
_COMMIT = re.compile(r"[0-9a-f]{40}")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}")
_SHA = re.compile(r"[0-9a-f]{64}")
_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?")
_PROBE_PATH = re.compile(r"[A-Za-z0-9_./-]+\.py")


@dataclass(frozen=True)
class SecurityCase:
    """Controller-owned expectations for one frozen probe. Never read from the target."""

    cve: str
    path: str
    sha256: str

    @classmethod
    def from_env(cls) -> SecurityCase | None:
        sha = os.getenv("JATAYU_PROBE_SHA256", "").strip().lower()
        if not sha:
            return None
        case = cls(
            cve=os.getenv("JATAYU_PROBE_CVE", "CVE-2026-87975").strip(),
            path=os.getenv("JATAYU_PROBE_PATH", "security_probe.py").strip(),
            sha256=sha,
        )
        case.validate()
        return case

    def validate(self) -> None:
        if not re.fullmatch(r"CVE-[0-9]{4}-[0-9]{4,}", self.cve):
            raise ValueError("JATAYU_PROBE_CVE must look like CVE-YYYY-NNNN")
        if not _SHA.fullmatch(self.sha256):
            raise ValueError("JATAYU_PROBE_SHA256 must be a 64-character hex SHA-256")
        if not _PROBE_PATH.fullmatch(self.path) or check_path(self.path) != self.path:
            raise ValueError("JATAYU_PROBE_PATH must be a safe relative .py path")


@dataclass
class Bundle:
    script: str
    patch_tgz: bytes
    deletes: str
    sources: list[dict] = field(default_factory=list)

    @property
    def script_sha256(self) -> str:
        return hashlib.sha256(self.script.encode()).hexdigest()

    @property
    def patch_sha256(self) -> str:
        return hashlib.sha256(self.patch_tgz).hexdigest()


def _patch_archive(patch: Patch | None) -> tuple[bytes, str]:
    buf = io.BytesIO()
    deletes: list[str] = []
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        for path, content in sorted((patch.files if patch else {}).items()):
            data = content.encode()
            info = tarfile.TarInfo(check_path(path))
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
        deletes = [check_path(p) for p in sorted(patch.deletes)] if patch else []
    return buf.getvalue(), "".join(f"{p}\n" for p in deletes)


def build(
    repo_url: str,
    commit: str,
    django_version: str,
    patch: Patch | None,
    case: SecurityCase | None,
) -> Bundle:
    """Generate the script and inline sources. All interpolated values are validated."""
    if not _URL.fullmatch(repo_url):
        raise ValueError("repo_url must be https://github.com/owner/repo")
    if not _COMMIT.fullmatch(commit):
        raise ValueError("source commit must be a 40-character SHA")
    if not _VERSION.fullmatch(django_version):
        raise ValueError("framework version must be exact")
    if case is not None:
        case.validate()
        if patch and (case.path in patch.files or case.path in patch.deletes):
            raise ValueError("the migration patch may not modify the frozen security probe")
    tgz, deletes = _patch_archive(patch)
    probe_path = case.path if case else ""
    script = _SCRIPT.format(
        repo_url=repo_url.rstrip("/"),
        commit=commit,
        django=django_version,
        probe=probe_path,
    )
    b = Bundle(script=script, patch_tgz=tgz, deletes=deletes)
    b.sources = [
        _inline(f"{HARNESS_DIR}/verify.sh", script.encode()),
        _inline(f"{HARNESS_DIR}/patch.tar.gz", tgz),
        _inline(f"{HARNESS_DIR}/deletes.txt", deletes.encode()),
    ]
    return b


def _inline(target: str, data: bytes) -> dict:
    return {
        "type": "inline",
        "target": target,
        "encoding": "base64",
        "content": base64.b64encode(data).decode(),
    }


# The harness never decides pass/fail. It only produces raw files.
_SCRIPT = r"""#!/usr/bin/env bash
# Jatayu verification harness (controller-owned; do not edit).
set -u
HERE="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
OUT="$HERE/out"; W="$HERE/work"
rm -rf "$OUT" "$W"; mkdir -p "$OUT" "$W"
rec() {{ echo "$2" > "$OUT/$1"; }}

git clone --quiet "{repo_url}" "$W/repo" > "$OUT/clone.log" 2>&1 || {{ rec clone.exit $?; echo done > "$OUT/DONE"; exit 0; }}
cd "$W/repo"
git checkout --quiet --detach "{commit}" >> "$OUT/clone.log" 2>&1
git rev-parse HEAD > "$OUT/head.txt"

# Apply the patch exactly: whole-file replacements from the archive, then deletions.
tar xzf "$HERE/patch.tar.gz" --no-same-owner -C "$W/repo" >> "$OUT/clone.log" 2>&1
while IFS= read -r p; do [ -n "$p" ] && rm -f -- "$W/repo/$p"; done < "$HERE/deletes.txt"

python3 --version > "$OUT/python.txt" 2>&1
python3 -m venv "$W/venv" && . "$W/venv/bin/activate"
pip install --disable-pip-version-check -q -r requirements.txt > "$OUT/install.log" 2>&1
REQ=$?
pip install --disable-pip-version-check -q "Django=={django}" "unittest-xml-reporting>=3.2" >> "$OUT/install.log" 2>&1
PIN=$?
# Either failure fails the install; record both so neither can mask the other.
echo "requirements=$REQ pinned=$PIN" >> "$OUT/install.log"
if [ "$REQ" -ne 0 ]; then rec install.exit "$REQ"; else rec install.exit "$PIN"; fi
python -c "import django; print(django.get_version())" > "$OUT/django.txt" 2>> "$OUT/install.log"

# Point Django's test runner at a JUnit writer without editing the project.
ORIG="$(python - <<'PY'
import re
m = re.search(r"DJANGO_SETTINGS_MODULE['\"]\s*,\s*['\"]([\w.]+)['\"]", open("manage.py").read())
print(m.group(1) if m else "")
PY
)"
ORIG="${{ORIG:-${{DJANGO_SETTINGS_MODULE:-}}}}"
mkdir -p "$W/shim"
cat > "$W/shim/jatayu_junit_settings.py" <<PY
from $ORIG import *  # noqa: F401,F403
TEST_RUNNER = "xmlrunner.extra.djangotestrunner.XMLTestRunner"
TEST_OUTPUT_DIR = "$OUT"
TEST_OUTPUT_FILE_NAME = "junit.xml"
PY
PYTHONPATH="$W/shim:$W/repo" timeout 900 python manage.py test --settings=jatayu_junit_settings --noinput --verbosity 2 > "$OUT/tests.stdout" 2> "$OUT/tests.stderr"
rec tests.exit $?
timeout 300 python manage.py check > "$OUT/check.stdout" 2> "$OUT/check.stderr"
rec check.exit $?

if [ -n "{probe}" ] && [ -f "{probe}" ]; then
  sha256sum "{probe}" | cut -d' ' -f1 > "$OUT/probe.sha256"
  timeout 300 python "{probe}" > "$OUT/probe.stdout" 2> "$OUT/probe.stderr"
  rec probe.exit $?
fi
echo done > "$OUT/DONE"
"""


# --- turning downloaded bytes into a report --------------------------------------------------


def _txt(art: dict[str, bytes], name: str) -> str | None:
    raw = art.get(name)
    return None if raw is None else raw.decode("utf-8", "replace").strip()


def _int(art: dict[str, bytes], name: str) -> int | None:
    v = _txt(art, name)
    return int(v) if v is not None and re.fullmatch(r"-?[0-9]+", v) else None


def _tail(text: str | None, n: int = 15) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def junit_failures(raw: bytes) -> list[Failure]:
    out = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    for tc in root.iter("testcase"):
        for tag in ("failure", "error"):
            node = tc.find(tag)
            if node is not None:
                name = f"{tc.get('classname', '')}.{tc.get('name', '')}".strip(".")
                detail = (node.get("message") or "") + "\n" + (node.text or "")
                out.append(Failure(test=name, trace_head=_tail(detail)))
    return out[:40]


def report_from_artifacts(
    art: dict[str, bytes],
    *,
    bundle: Bundle,
    returned: dict[str, bytes],
    commit: str,
    django_version: str,
    case: SecurityCase | None,
) -> VerifyReport:
    """Build the report from raw sandbox files only, and decide whether they're trustworthy."""
    problems: list[str] = []
    if "DONE" not in art:
        problems.append("harness did not finish")
    if returned.get("verify.sh") is None or (
        hashlib.sha256(returned["verify.sh"]).hexdigest() != bundle.script_sha256
    ):
        problems.append("harness script in sandbox differs from the one uploaded")
    if returned.get("patch.tar.gz") is None or (
        hashlib.sha256(returned["patch.tar.gz"]).hexdigest() != bundle.patch_sha256
    ):
        problems.append("patch archive in sandbox differs from the one uploaded")
    if returned.get("deletes.txt") is None or returned["deletes.txt"] != bundle.deletes.encode():
        problems.append("deletion manifest in sandbox differs from the one uploaded")
    head = _txt(art, "head.txt")
    if head != commit:
        problems.append(f"checked-out commit {head!r} is not the source commit")
    installed = _txt(art, "django.txt")
    if installed != django_version:
        problems.append(f"installed Django {installed!r} is not {django_version}")

    install_exit = _int(art, "install.exit")
    tests_exit = _int(art, "tests.exit")
    checks_exit = _int(art, "check.exit")
    if tests_exit is None:
        problems.append("test exit status missing")

    failures: list[Failure] = []
    if art.get("junit.xml") is not None:
        try:
            suite = parse_junit(art["junit.xml"])
            failures = junit_failures(art["junit.xml"])
        except ArtifactError as e:
            problems.append(f"JUnit rejected: {e}")
            suite = SuiteCounts(errors=1)
    else:
        # No report means the suite never ran (e.g. the app fails to start). That is a
        # verified failure, not missing evidence, as long as the exit status shows it.
        suite = SuiteCounts(errors=1)
        if tests_exit == 0:
            problems.append("tests exited 0 without a JUnit report")
        failures = [
            Failure(test="test run did not start", trace_head=_tail(_txt(art, "tests.stderr")))
        ]

    check_issues = []
    if checks_exit not in (0, None):
        check_issues = [
            ln for ln in _tail(_txt(art, "check.stderr"), 10).splitlines() if ln.strip()
        ] or [f"manage.py check exited {checks_exit}"]

    exploits: list[ExploitResult] = []
    if case is not None:
        exploits.append(_probe(art, case, installed or django_version))

    report = VerifyReport(
        python_version=_txt(art, "python.txt") or "",
        django_version=installed or "",
        test_command="python manage.py test --verbosity 2 (JUnit via unittest-xml-reporting)",
        suite=suite,
        failures=failures,
        check=check_issues,
        deprecation_warnings=None,
        exploits=exploits,
        install_ok=install_exit == 0,
        tests_exit_code=tests_exit,
        checks_exit_code=checks_exit,
        notes="; ".join(problems) or "Built from raw sandbox files retrieved via the Files API.",
    )
    report.artifacts_verified = not problems
    report.evidence_source = "sandbox_artifacts" if not problems else "agent_summary"
    return report


def _probe(art: dict[str, bytes], case: SecurityCase, version: str) -> ExploitResult:
    def err(why: str) -> ExploitResult:
        return ExploitResult(
            cve=case.cve,
            django_version=version,
            blocked=False,
            outcome="error",
            benign_control_passed=False,
            probe_sha256=case.sha256,
            evidence=why,
        )

    if _txt(art, "probe.sha256") != case.sha256:
        return err("probe file in sandbox does not match the frozen SHA-256 (or did not run)")
    exit_code = _int(art, "probe.exit")
    if exit_code is None or art.get("probe.stdout") is None:
        return err("probe produced no exit status or stdout")
    try:
        result = parse_django_probe(
            art["probe.stdout"],
            exit_code=exit_code,
            expected_cve=case.cve,
            expected_version=version,
            expected_sha256=case.sha256,
        )
    except ArtifactError as e:
        return err(f"probe output rejected: {e}; stderr: {_tail(_txt(art, 'probe.stderr'), 5)}")
    result.evidence = "Raw probe stdout and exit status retrieved from the sandbox filesystem."
    return result


def save(art: dict[str, bytes], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in art.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
