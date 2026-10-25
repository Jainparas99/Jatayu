import json
from datetime import date
from pathlib import Path

from unpinned.fleet.__main__ import main
from unpinned.fleet.scan import latest, save, scan_many, scan_target

TODAY = date(2026, 10, 25)


def _repo(tmp_path: Path, name: str, files: dict[str, str]) -> str:
    root = tmp_path / name
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return str(root)


def test_ranks_repos_by_worst_component(tmp_path: Path):
    old = _repo(tmp_path, "old", {"requirements.txt": "Django==3.2.25\n"})
    mid = _repo(tmp_path, "mid", {"requirements.txt": "Django==4.2.30\n"})
    new = _repo(tmp_path, "new", {"requirements.txt": "Django==5.2.18\n"})
    result = scan_many([new, mid, old], TODAY)
    assert [r["target"] for r in result["repos"]] == [old, mid, new]
    assert [r["severity"] for r in result["repos"]] == ["critical", "high", "none"]
    s = result["summary"]
    assert (s["repos"], s["eol_components"], s["jatayu_ready"], s["repos_with_eol"]) == (3, 2, 2, 2)


def test_engine_labels(tmp_path: Path):
    r = scan_target(_repo(tmp_path, "r", {"Gemfile.lock": "    rails (7.0.8)\n"}), TODAY)
    (c,) = r.components
    assert (c.engine, c.severity) == ("roadmap", "critical")  # 572 days unpatched


def test_bad_target_is_reported_not_raised(tmp_path: Path):
    r = scan_target(str(tmp_path / "missing"), TODAY)
    assert r.error and r.severity == "none"


def test_save_and_latest(tmp_path: Path):
    res = scan_many([_repo(tmp_path, "a", {"requirements.txt": "Django==4.2.1\n"})], TODAY)
    save(res, tmp_path / "runs")
    assert latest(tmp_path / "runs")["summary"] == res["summary"]


def test_cli_fail_on_and_annotations(tmp_path: Path, capsys):
    repo = _repo(tmp_path, "a", {"requirements.txt": "Django==4.2.1\n"})
    assert main(["scan", repo, "--fail-on", "eol", "--github"]) == 1
    out = capsys.readouterr().out
    assert (
        "::error file=requirements.txt,line=1,title=Jatayu::Django 4.2.1 reached end of life" in out
    )
    assert main(["scan", repo, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["eol_components"] == 1
