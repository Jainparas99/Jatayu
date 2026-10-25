.PHONY: setup skills test lint fmt ping serve

setup:
	uv sync

skills:
	-npx -y skills add google-gemini/gemini-skills --skill gemini-api-dev
	-npx -y skills add google-gemini/gemini-skills --skill gemini-live-api-dev
	-agy plugin install https://github.com/google-gemini/gemini-skills

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

fmt:
	uv run ruff check --fix . && uv run ruff format .

ping:
	uv run jatayu ping

serve:
	uv run jatayu serve
