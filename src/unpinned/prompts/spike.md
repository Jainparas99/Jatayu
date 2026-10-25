You are checking whether a Django project can be tested in this sandbox. Do not modify the project and never run `git push`.

1. `git clone --depth 1 {repo_url} repo && cd repo`
2. Report `python --version`.
3. Create a virtualenv. Install the project's requirements (look for requirements*.txt, pyproject.toml, setup.py). Then install `Django=={django_version}` explicitly.
4. Detect and run the project's test command (`python manage.py test`, `pytest`, or a tox env). Use the settings module the project's own docs or CI use.
5. Count Python files (excluding migrations and virtualenvs).

Reply with ONLY this JSON, no prose:
{{"python_version": str, "django_version": str, "install_ok": bool, "install_seconds": number,
  "test_command": str, "suite": {{"passed": int, "failed": int, "errors": int, "skipped": int}},
  "test_seconds": number, "python_files": int, "notes": str}}
