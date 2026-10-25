from pathlib import Path

import pytest

from unpinned import adapters
from unpinned.adapters.django import bump, notes_urls
from unpinned.pack import pack


def test_django_notes_cover_every_release_in_between():
    urls = notes_urls("4.2.30", "5.2.18")
    assert [u.rsplit("/", 2)[-2] for u in urls] == ["5.0", "5.1", "5.2"]
    with pytest.raises(ValueError):
        notes_urls("5.2", "4.2")


def test_django_bump_changes_only_the_pin():
    files = {
        "requirements.txt": "Django>=4.2,<5  # web\nrequests==2.0\n",
        "pyproject.toml": 'dependencies = ["django>=4.2,<5", "rich"]\n',
        "app/views.py": "import django\n",
    }
    p = bump(files, "5.2.18")
    assert p.files["requirements.txt"] == "Django==5.2.18  # web\nrequests==2.0\n"
    assert p.files["pyproject.toml"] == 'dependencies = ["Django==5.2.18", "rich"]\n'
    assert "app/views.py" not in p.files


def test_detect_django(tmp_path: Path):
    (tmp_path / "manage.py").write_text("")
    assert adapters.detect(tmp_path).name == "django"
    other = tmp_path / "other"
    other.mkdir()
    (other / "Gemfile").write_text("gem 'rails', '~> 6.1'\n")
    assert adapters.detect(other) is None


def test_generic_reads_every_text_file_any_language(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "Gemfile").write_text("gem 'rails'\n")
    (tmp_path / "app/user.rb").write_text("class User; end\n")
    (tmp_path / "src.go").write_text("package main\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\0\0binary")
    (tmp_path / ".env").write_text("SECRET=1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/x.js").write_text("x")
    a = adapters.get("generic", framework="Rails", language="Ruby", test_command="bin/rails test")
    b = pack(tmp_path, adapter=a)
    assert set(b.files) == {"Gemfile", "app/user.rb", "src.go"}


def test_generic_requires_a_test_command():
    with pytest.raises(ValueError):
        adapters.get("generic", test_command=" ")


def test_unknown_adapter():
    with pytest.raises(ValueError):
        adapters.get("cobol")
