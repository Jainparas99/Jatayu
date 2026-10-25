from pathlib import Path

from unpinned.fleet.detect import detect


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_django_lock_beats_requirements_constraint(tmp_path: Path):
    _write(tmp_path, "requirements.txt", "requests==2\nDjango>=4.2,<5\n")
    _write(tmp_path, "poetry.lock", '[[package]]\nname = "django"\nversion = "4.2.11"\n')
    (f,) = [x for x in detect(tmp_path) if x.product == "django"]
    assert (f.version, f.source, f.line, f.confidence) == ("4.2.11", "poetry.lock", 3, "locked")


def test_requirements_line_numbers_and_ignores_lookalikes(tmp_path: Path):
    _write(tmp_path, "requirements.txt", "django-filter==23.1\n\nDjango==3.2.25  # old\n")
    (f,) = detect(tmp_path)
    assert (f.product, f.version, f.line, f.confidence) == ("django", "3.2.25", 3, "pinned")


def test_rails_spring_node_python(tmp_path: Path):
    _write(tmp_path, "rb/Gemfile.lock", "GEM\n  specs:\n    rails (6.1.7.10)\n      actionpack\n")
    _write(
        tmp_path,
        "java/pom.xml",
        "<project>\n<parent>\n<groupId>org.springframework.boot</groupId>\n"
        "<artifactId>spring-boot-starter-parent</artifactId>\n<version>2.7.18</version>\n"
        "</parent>\n</project>\n",
    )
    _write(tmp_path, "web/.nvmrc", "v18.19.0\n")
    _write(tmp_path, "Dockerfile", "FROM python:3.9-slim\n")
    got = {(f.product, f.version, f.source, f.line) for f in detect(tmp_path)}
    assert got == {
        ("rails", "6.1.7.10", "rb/Gemfile.lock", 3),
        ("spring-boot", "2.7.18", "java/pom.xml", 5),
        ("nodejs", "18.19.0", "web/.nvmrc", 1),
        ("python", "3.9", "Dockerfile", 1),
    }


def test_gradle_kts_and_package_engines(tmp_path: Path):
    _write(
        tmp_path,
        "build.gradle.kts",
        'plugins {\n  id("org.springframework.boot") version "3.1.5"\n}\n',
    )
    _write(
        tmp_path, "package.json", '{\n  "name": "x",\n  "engines": {\n    "node": ">=16"\n  }\n}\n'
    )
    got = {(f.product, f.version, f.line) for f in detect(tmp_path)}
    assert got == {("spring-boot", "3.1.5", 2), ("nodejs", "16", 4)}


def test_skips_vendored_and_deep_dirs(tmp_path: Path):
    _write(tmp_path, "node_modules/x/.nvmrc", "16\n")
    _write(tmp_path, "a/b/c/d/requirements.txt", "Django==3.2\n")
    assert detect(tmp_path) == []


def test_ruby_runtime_versions(tmp_path: Path):
    _write(tmp_path, "a/.ruby-version", "ruby-3.1.4\n")
    _write(tmp_path, "b/Gemfile", "source 'https://rubygems.org'\nruby '3.2.2'\ngem 'rack'\n")
    gemspec = "Gem::Specification.new do |s|\n  s.required_ruby_version = '>= 2.7.6'\nend\n"
    _write(tmp_path, "c/x.gemspec", gemspec)
    _write(tmp_path, "d/Dockerfile", "FROM ruby:3.0-slim\n")
    got = {(f.product, f.version, f.source, f.confidence) for f in detect(tmp_path)}
    assert got == {
        ("ruby", "3.1.4", "a/.ruby-version", "pinned"),
        ("ruby", "3.2.2", "b/Gemfile", "pinned"),
        ("ruby", "2.7.6", "c/x.gemspec", "declared"),
        ("ruby", "3.0", "d/Dockerfile", "pinned"),
    }
