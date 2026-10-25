# Jatayu

Framework migration tooling powered by Gemini 4 Argon, with independent verification and human review. Built for the Gemini 4 Argon SF Hackathon on October 25, 2026.

Argon generates coordinated changes across a repository. Antigravity is intended to execute the verification loop, with recorded results and a reviewable patch before human approval. Django is the first ecosystem adapter; the adapter architecture is being extended for other stacks.

**Current state:** local controller tests, strict raw-artifact parsers, and one purpose-built Django security regression fixture are implemented and tested. A completed Argon migration, independently verified cloud run, target application benchmark, and PR publication are still pending.

## Run locally

Requires Python 3.12 or newer and uv.

```sh
git clone https://github.com/Jainparas99/Jatayu.git
cd Jatayu
uv sync --locked
make test lint
uv run jatayu doctor
uv run jatayu serve
```

Open http://127.0.0.1:8000 for the evidence review page. With no saved migration runs, the page shows no evidence and keeps publication disabled.

Copy `.env.example` to `.env` and configure `GEMINI_API_KEY` locally for provider testing. Run `make ping` to test access. Credentials belong in the local environment and are excluded from Git.

Project settings use the `JATAYU_*` prefix shown in `.env.example`. The original settings prefix remains accepted for existing local setups. The internal Python module is `unpinned`; the public package and command are `jatayu`.

## Prepare an input without API access

The `prepare` command clones a public GitHub input, pins its source commit, selects
which files to read, and saves a requested execution recipe under `runs/`. It does
not install the target, execute its tests, fetch upgrade notes, or call a model.

```sh
uv run jatayu prepare https://github.com/OWNER/REPO --adapter django
```

For another ecosystem, supply the framework, language, versions, commands and
upgrade-note URLs explicitly:

```sh
uv run jatayu prepare https://github.com/OWNER/REPO \
  --adapter generic --framework FRAMEWORK --language LANGUAGE \
  --from-version SOURCE_VERSION --target TARGET_VERSION \
  --install-cmd "INSTALL_COMMAND" --test-cmd "TEST_COMMAND" \
  --notes-url https://example.com/official-upgrade-notes
```

Generic input preparation is available. Generic sandbox verification and completed
migrations in other ecosystems remain unimplemented. Prepared recipes carry no
verification or approval authority, and their runtime versions are requested inputs,
not measured results. The live `run` command currently accepts `--adapter django`.
Its baseline must have independently verified sandbox evidence before migration starts.

## Reproduce the local security fixture

Install Django 4.2.30 and 5.2.18 into separate Python 3.12 environments, then run:

```sh
uv run jatayu prove-fixture /path/to/old-env/bin/python /path/to/new-env/bin/python
```

The unchanged HTTP test-client probe reproduces the editable-primary-key formset issue on 4.2.30 and blocks it on 5.2.18; a normal edit succeeds on both. Raw proof is saved under `runs/*-local-fixture-*/`.

This purpose-built, in-memory fixture establishes only its own behavior. It is not evidence of exposure in an arbitrary target repository, an Argon-generated migration, or a cloud benchmark.

## Verification and approval

Raw artifact parsers check testcase records, process outcomes, probe hashes, and runtime versions. Parsing alone does not authenticate sandbox execution. See the [artifact parsing contract](src/unpinned/artifacts/README.md) and [security probe notes](security_tests/README.md).

Independent cloud artifact retrieval and provenance remain incomplete. Model summaries cannot certify their own results. Publication stays unavailable until the verification and exact-patch approval flow is complete.

## Built today

Claude Code supplied the initial scaffold and ecosystem adapter definitions. Codex repaired evidence gates, provider response handling, sandbox continuation, patch safety, and review behavior; added the owned security fixture, raw-artifact parsers, and regression tests; and prepared the Jatayu public branding. Gemini 4 Argon is the intended migration lead; Antigravity is the intended remote execution environment.

Commit range is pending the initial commit. No completed migration benchmark is claimed. A target repository, its license credit and immutable commit, comparable baseline results, live migration runtime, and model spend still need to be recorded.

## License

[MIT](LICENSE) — Copyright 2026 Paras Jain.


## Runs and Fleet workspace

`uv run jatayu serve` starts the shared server at `http://127.0.0.1:8000`:

- **Runs** (`/`): saved run history, independent evidence status, blockers, full patch SHA-256,
  diff inspection/download, and an approval button bound to the reviewed patch.
- **Fleet** (`/fleet`): find unsupported framework/runtime pins. Also available as
  `uv run jatayu fleet scan /path/to/repo --save`.
- **Configuration** (in Runs): credential presence flags and safe execution defaults.
  Credential values are never returned by this view.

Set `JATAYU_DASHBOARD_TOKEN` in the server environment to allow write requests. The browser's
password field keeps its token only in tab memory. The server validates it on each action.
Reads require your hosting platform's access controls; see [deployment instructions](deploy/README.md).
Use the existing Dockerfile and `unpinned.server:app` for deployment. Containers need persistent
storage for durable run artifacts; Cloud Run's default filesystem is ephemeral.

Migrations currently start from the CLI on the server. Browser launch and PR publication are
unavailable. The approval button stays disabled until both evidence gates and publication support
are ready. Local fixture proofs and model summaries never count as verified sandbox results.
