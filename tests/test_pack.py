from unpinned.pack import pack


def test_pack_includes_code_and_skips_noise(tmp_path):
    (tmp_path / "app/migrations").mkdir(parents=True)
    (tmp_path / "app/views.py").write_text("x = 1\n")
    (tmp_path / "app/migrations/0001_initial.py").write_text("ops\n")
    (tmp_path / "app/migrations/__init__.py").write_text("")
    (tmp_path / "requirements.txt").write_text("Django>=4.2,<5\n")
    (tmp_path / ".env").write_text("SECRET=1\n")
    (tmp_path / "static").mkdir()
    (tmp_path / "static/app.js").write_text("js")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/config").write_text("x")
    b = pack(tmp_path)
    assert set(b.files) == {
        "app/views.py",
        "app/migrations/__init__.py",
        "app/migrations/0001_initial.py",
        "requirements.txt",
    }
    assert "<<<FILE app/views.py>>>" in b.text
    assert len(b.sha256) == 64


def test_pack_does_not_follow_symlinks_to_private_files(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    secret = tmp_path / "private.py"
    secret.write_text("PRIVATE_VALUE")
    (root / "settings.py").symlink_to(secret)
    assert "PRIVATE_VALUE" not in pack(root).text
