import pytest

from unpinned.parse import UnsafePath, check_path, parse, unified_diff

OUT = """<<<FILE app/views.py>>>
from django.http import HttpResponse
<<<END FILE>>>
<<<FILE app/new_module.py>>>
X = 1
<<<END FILE>>>
<<<FILE ../evil.py>>>
pwn
<<<END FILE>>>
<<<FILE .github/workflows/ci.yml>>>
on: push
<<<END FILE>>>
<<<FILE .env>>>
KEY=1
<<<END FILE>>>
<<<DELETE app/old.py>>>
<<<SUMMARY>>>
- app/views.py: url() removed in 4.0
- app/new_module.py: new helper
<<<END SUMMARY>>>
"""


def test_parse_accepts_known_and_declared_new_files():
    p = parse(OUT, known_files={"app/views.py", "app/old.py"})
    assert set(p.files) == {"app/views.py", "app/new_module.py"}
    assert p.files["app/views.py"] == "from django.http import HttpResponse\n"
    assert p.deletes == ["app/old.py"]
    assert p.summary["app/views.py"].startswith("url()")
    assert not p.truncated


def test_parse_rejects_unsafe_paths():
    p = parse(OUT, known_files={"app/views.py"})
    reasons = dict(p.rejected)
    assert reasons["../evil.py"] == "path escapes repo"
    assert reasons[".github/workflows/ci.yml"] == "protected path"
    assert reasons[".env"] == "secrets file"


def test_parse_rejects_undeclared_unknown_file():
    out = "<<<FILE app/surprise.py>>>\nx\n<<<END FILE>>>"
    p = parse(out, known_files={"app/views.py"})
    assert p.files == {}
    assert p.rejected[0][0] == "app/surprise.py"


def test_truncated_output_is_flagged():
    out = "<<<FILE a.py>>>\nx\n<<<END FILE>>>\n<<<FILE b.py>>>\nhalf a fi"
    p = parse(out)
    assert p.truncated
    assert set(p.files) == {"a.py"}


@pytest.mark.parametrize(
    "bad", ["/etc/passwd", "C:/x.py", "a\\b.py", ".git/config", "", "x/../../y"]
)
def test_check_path_rejects(bad):
    with pytest.raises(UnsafePath):
        check_path(bad)


def test_check_path_normalizes():
    assert check_path("./app/./views.py") == "app/views.py"


def test_unified_diff():
    d = unified_diff("a.py", "x = 1\n", "x = 2\n")
    assert "-x = 1" in d and "+x = 2" in d


@pytest.mark.parametrize(
    "path",
    [
        ".",
        "./",
        ".github/workflows",
        "security_tests/probe.py",
        "app/tests/test_x.py",
        "app/test_views.py",
        "a\x00.py",
    ],
)
def test_independent_tests_and_invalid_paths_are_protected(path):
    with pytest.raises(UnsafePath):
        check_path(path)


def test_rejected_and_truncated_patches_cannot_be_applied():
    from unpinned.parse import validate_patch

    for output in ("<<<FILE a.py>>>\nx", "<<<DELETE .env>>>"):
        with pytest.raises(ValueError):
            validate_patch(parse(output))


def test_conflicting_write_and_delete_is_rejected():
    patch = parse("<<<FILE a.py>>>\nx\n<<<END FILE>>>\n<<<DELETE a.py>>>", {"a.py"})
    assert patch.rejected
