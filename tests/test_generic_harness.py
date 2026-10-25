# ruff: noqa: E501
import hashlib
from dataclasses import dataclass, field

import pytest

from unpinned.parse import Patch
from unpinned.verify import generic_harness as gh

URL = "https://github.com/expressjs/cors"
COMMIT = "5317ebe670db2aaebc1d496eb5d33493deefb3ed"


@dataclass
class Spec:
    framework: str = "Express"
    language: str = "JavaScript"
    source_version: str = "4.21.2"
    target_version: str = "5.3.0"
    install_command: str = (
        "npm install --no-audit --no-fund && npm install --no-save express@{version}"
    )
    test_command: str = "npx mocha --reporter xunit --reporter-option output=test-results.xml"
    version_command: str = "node -p \"require('express/package.json').version\""
    runtime_command: str = "node --version"
    junit_path: str = "test-results.xml"
    notes_urls: list[str] = field(
        default_factory=lambda: ["https://expressjs.com/en/guide/migrating-5.html"]
    )
    check_command: str | None = "npx eslint ."
    working_directory: str = "."
    timeout_seconds: int = 900

    def render(self, command: str, version: str) -> str:
        return command.replace("{version}", version)


JUNIT = b"""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Mocha Tests" tests="2" failures="0" errors="0" skipped="0" timestamp="t" time="0.1">
<testcase classname="cors" name="passes" time="0.01"/>
<testcase classname="cors" name="sets origin" time="0.01"/>
</testsuite>"""

TRACKED = {
    "index.js": b"module.exports = 1\n",
    "test/test.js": b"it('x')\n",
    "package.json": b'{"devDependencies":{"express":"4.21.2"}}\n',
}


def _manifest(tree: dict[str, str]) -> bytes:
    return "".join(f"{d}  {p}\n" for p, d in sorted(tree.items())).encode()


def _setup(version="5.3.0", patch=None, **over):
    spec = Spec()
    b = gh.build(URL, COMMIT, spec, version, patch)
    tree = gh.expected_manifest(TRACKED, patch)
    after = dict(tree) | {"test-results.xml": "f" * 64, "package-lock.json": "e" * 64}
    art = {
        "DONE": b"done",
        "head.txt": COMMIT.encode(),
        "tree.before": _manifest(tree),
        "tree.after": _manifest(after),
        "runtime.txt": b"v22.11.0\n",
        "version.txt": f"{version}\n".encode(),
        "version.exit": b"0",
        "install.exit": b"0",
        "tests.exit": b"0",
        "junit.status": b"ok",
        "junit.xml": JUNIT,
        "check.exit": b"0",
    }
    art.update(over)
    art = {k: v for k, v in art.items() if v is not None}
    return spec, b, tree, art


def _report(spec, b, tree, art, returned=None):
    return gh.report_from_artifacts(
        art,
        bundle=b,
        returned=b.expected_inputs() if returned is None else returned,
        commit=COMMIT,
        expected_tree=tree,
        spec=spec,
    )


def test_build_renders_versions_and_mounts_every_command():
    spec = Spec()
    b = gh.build(URL, COMMIT, spec, "5.3.0", None)
    assert b.commands["install"].endswith("express@5.3.0")
    assert set(b.commands) == {"install", "test", "version", "runtime", "check"}
    targets = {s["target"] for s in b.sources}
    assert {
        "jatayu/verify.sh",
        "jatayu/cmd/test.sh",
        "jatayu/patch.tar.gz",
        "jatayu/deletes.txt",
    } <= targets
    assert "pip install" not in b.script and "manage.py" not in b.script  # nothing Django-specific


@pytest.mark.parametrize(
    "field_name,value",
    [("junit_path", "../x.xml"), ("working_directory", "/etc"), ("timeout_seconds", 5)],
)
def test_build_rejects_unsafe_recipe_values(field_name, value):
    spec = Spec()
    setattr(spec, field_name, value)
    with pytest.raises(ValueError):
        gh.build(URL, COMMIT, spec, "5.3.0", None)


def test_green_target_is_verified_but_security_not_assessed():
    spec, b, tree, art = _setup()
    r = _report(spec, b, tree, art)
    assert r.artifacts_verified and r.tree_verified and r.security_assessed is False
    assert (r.suite.passed, r.framework_version, r.runtime_version) == (2, "5.3.0", "22.11.0")
    assert not r.exploits
    assert gh.is_green(r, r, require_check=True) == []


@pytest.mark.parametrize(
    "over,expect",
    [
        ({"version.txt": b"4.21.2\n"}, "version"),
        ({"head.txt": b"b" * 40}, "source commit"),
        ({"junit.status": b"symlink", "junit.xml": None}, "symlink"),
        ({"junit.status": b"missing", "junit.xml": None}, "without a JUnit"),
        ({"tests.exit": b"124"}, "timed out"),
        ({"DONE": None}, "did not finish"),
        ({"tree.after": None}, "manifest"),
    ],
)
def test_untrustworthy_runs_fail_closed(over, expect):
    spec, b, tree, art = _setup(**over)
    r = _report(spec, b, tree, art)
    assert not r.artifacts_verified and expect in r.notes


def test_tampered_command_file_is_detected():
    spec, b, tree, art = _setup()
    returned = b.expected_inputs() | {"cmd/test.sh": b"exit 0"}
    r = _report(spec, b, tree, art, returned)
    assert not r.artifacts_verified and "cmd/test.sh" in r.notes


def test_worktree_must_match_commit_plus_patch_and_not_change_during_run():
    patch = Patch(files={"index.js": "module.exports = 2\n"})
    spec, b, tree, art = _setup(patch=patch)
    assert _report(spec, b, tree, art).tree_verified
    # Agent edits a test before the run: the before-manifest no longer matches.
    bad_before = dict(tree) | {"test/test.js": "0" * 64}
    r = _report(spec, b, tree, art | {"tree.before": _manifest(bad_before)})
    assert not r.tree_verified and "differs from source commit + patch" in r.notes
    # A test file changes during the run.
    bad_after = dict(tree) | {"test/test.js": "1" * 64}
    r = _report(spec, b, tree, art | {"tree.after": _manifest(bad_after)})
    assert "changed during the run" in r.notes


def test_suite_may_not_shrink_or_gain_skips():
    spec, b, tree, art = _setup()
    base = _report(spec, b, tree, art)
    fewer = JUNIT.replace(b'tests="2"', b'tests="1"').replace(
        b'<testcase classname="cors" name="sets origin" time="0.01"/>\n', b""
    )
    r = _report(spec, b, tree, art | {"junit.xml": fewer})
    assert any("shrank" in x for x in gh.is_green(r, base, require_check=True))


def test_expected_manifest_applies_patch():
    patch = Patch(files={"new.js": "x\n"}, deletes=["index.js"])
    m = gh.expected_manifest(TRACKED, patch)
    assert "index.js" not in m and m["new.js"] == hashlib.sha256(b"x\n").hexdigest()
