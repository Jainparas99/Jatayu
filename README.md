# Jatayu

**Find applications running on frameworks that no longer receive security fixes, upgrade them with Gemini 4 Argon, verify the result in a sandbox, and publish only with human approval.**

Django 4.2 stopped receiving security patches on April 7, 2026. Every framework reaches the same point, and the fix is always the upgrade that touches every file. Jatayu turns that backlog item into a reviewable, evidence-backed change.

| Capability | What it does | Status |
|---|---|---|
| **Fleet** | Reads dependency manifests and lock files across repositories and ranks every end-of-life framework and runtime, with file and line evidence | Available |
| **Upgrade engine** | Gemini 4 Argon reads the whole repository plus the official upgrade notes in one context and writes every changed file in a single long-decode response | Verified end to end on Django 4.2 → 5.2 |
| **Verification** | An Antigravity managed agent runs a controller-owned harness; Jatayu downloads the raw JUnit XML, logs, exit codes and probe output through the Files API and builds the report from those bytes only | Working; see results below |
| **Review and approval** | Evidence, blockers and the patch SHA-256 on one page; nothing is published without explicit approval of that exact patch | Review implemented; PR publication disabled |

## Results

Measured on 2026-10-25 against [jatayu-demo-app](https://github.com/Jainparas99/jatayu-demo-app) at commit `554e82b`, a small Django 4.2 application written for this purpose that uses six APIs removed in Django 5.0/5.1 and contains a model formset with an editable primary key. Saved under [`runs/20261025-141628-unpinned-d39bc104`](runs/20261025-141628-unpinned-d39bc104).

| Run | Django | Application tests | CVE-2026-87975 probe | Evidence |
|---|---|---|---|---|
| Before upgrade | 4.2.30 | 25 / 25 pass | **attack succeeds**, benign control passes | raw sandbox artifacts |
| Version bump only (B0) | 5.2.18 | suite does not start: `Meta.index_together` removed | not reached | agent-reported (recorded before the artifact harness) |
| **Jatayu (Gemini 4 Argon)** | **5.2.18** | **25 / 25 pass** | **attack blocked**, benign control passes | **raw sandbox artifacts** |

- **One pass, no repairs:** Argon planned 16 breaking changes and wrote all 9 changed files (settings, models, migration, services, template and three test files) in a single response. The first verification was green, with 0 review blockers.
- **Same probe both times:** the frozen probe's SHA-256 is `179c4224…` before and after; the migration patch is not allowed to touch it.
- **Tests edited, not weakened:** test edits are limited to removed APIs (`assertQuerysetEqual` → `assertQuerySetEqual`, `override_settings` without removed settings). The parser rejects edits that remove tests or assertions or add skips, and the verified suite may not shrink below the baseline count.
- **Cost and time:** migration call 26,348 input / 5,625 output tokens; whole run 6 min 52 s including baseline and verification (about 1.5 min per sandbox verification).

The demo application is intentionally small. It shows the full loop with real evidence; it is not a benchmark of Argon's long-context scale.

## How it works

```
repositories ──► FLEET ──► ranked list of end-of-life frameworks and runtimes
                                │  choose a target
                                ▼
                 PACK      whole repository + official upgrade notes
                 PLAN      gemini-4-argon, thinking "high": every breaking change, cross-checked
                 MIGRATE   gemini-4-argon, background long decode: all changed files in one response
                 VERIFY    Antigravity sandbox: install, project tests, checks, security probe (raw artifacts)
                 REPAIR    failures → Argon (previous_interaction_id) → re-verify, bounded attempts
                 REVIEW    evidence gate + patch SHA-256 → human approval → pull request
```

Evidence rules are enforced in code, not by the model:

- A security claim requires the same frozen probe to **succeed as an attack before** the upgrade and be **blocked after** it, with a benign control passing on both.
- Empty test suites, skipped probes, timeouts and model-written summaries never count as passing.
- Approval is bound to the SHA-256 of the reviewed patch. A different patch needs a new review.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/Jainparas99/Jatayu.git
cd Jatayu
uv sync --locked
cp .env.example .env          # set GEMINI_API_KEY
make test lint
uv run jatayu doctor          # shows which credentials are configured (never their values)
uv run jatayu ping            # one gemini-4-argon call
uv run jatayu serve           # http://127.0.0.1:8000  (Runs)  and  /fleet  (Fleet)
```

## Usage

**Find end-of-life frameworks across repositories**

```sh
uv run jatayu fleet scan ./service-a https://github.com/OWNER/REPO --save
uv run jatayu fleet scan @repos.txt --fail-on eol        # one target per line
```

Fleet recognizes Django, Ruby on Rails, Spring Boot, Python and Node.js. Support dates come from [endoflife.date](https://endoflife.date); `uv run python -m unpinned.fleet refresh-eol` updates them.

**Upgrade a repository**

```sh
uv run jatayu spike   https://github.com/OWNER/REPO                 # can the sandbox install and test it?
uv run jatayu baseline https://github.com/OWNER/REPO --mode b0       # version bump only, for comparison
uv run jatayu run     https://github.com/OWNER/REPO --adapter django
uv run jatayu report                                                # results table from saved runs
```

**Prepare any repository (no API calls)**

```sh
uv run jatayu prepare https://github.com/OWNER/REPO \
  --adapter generic --framework FRAMEWORK --language LANGUAGE \
  --from-version SOURCE_VERSION --target TARGET_VERSION \
  --install-cmd "INSTALL_COMMAND" --test-cmd "TEST_COMMAND" \
  --notes-url https://example.com/official-upgrade-notes
```

Preparation clones the input, pins the source commit, selects files and saves an execution recipe under `runs/`. It does not install, test or call a model.

**Reproduce the security fixture**

```sh
uv run jatayu prove-fixture /path/to/django-4.2.30-env/bin/python /path/to/django-5.2.18-env/bin/python
```

The unchanged probe reproduces CVE-2026-87975 (model formsets with editable primary keys) on 4.2.30 and is blocked on 5.2.18; a normal edit succeeds on both. Raw output is saved under `runs/`. This purpose-built fixture establishes only its own behavior, not exposure in any other application.

## Ecosystem support

| Adapter | Language | Fleet detection | Upgrade engine |
|---|---|---|---|
| Django | Python | Yes | Verified end to end (4.2 → 5.2) |
| Ruby on Rails | Ruby | Yes | Roadmap |
| Spring Boot | Java | Yes | Roadmap |
| Generic | Any | — | Input preparation only |

Everything ecosystem-specific lives in `src/unpinned/adapters/`: files to read, how to bump the version pin, upgrade-note sources, install/test/check commands and the rule-based baseline. Roadmap adapters cannot be selected for a run until a verified run exists.

## Security model

- **Secrets:** read from the environment or the Gemini Credentials API at runtime; never committed, logged or placed in a model prompt.
- **Sandbox network:** the verification agent may reach PyPI and GitHub only.
- **Server access:** reads follow your hosting platform's access controls. Every state-changing request (scan, approve) requires `Authorization: Bearer $JATAYU_DASHBOARD_TOKEN`; without it the server is read-only.
- **Inputs over HTTP:** Fleet accepts only public `https://github.com/owner/repo` URLs, never local paths.
- **Model output:** generated patches are parsed with path checks that reject anything outside the repository, `.git/`, CI workflows, secrets files and independent security probes.

## Deployment

The deployable application is `unpinned.server:app` (Runs, Fleet and the review API). See [deploy/README.md](deploy/README.md) for Docker, Cloud Run (private by default) and the GitHub Action that flags end-of-life pins in pull requests.

## Configuration

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini API access |
| `GITHUB_TOKEN` | Registered with the Credentials API for approved pull requests |
| `JATAYU_FORK_OWNER` | Pull requests go only to forks owned by this account |
| `JATAYU_TARGET_DJANGO`, `JATAYU_BASELINE_DJANGO` | Exact target and baseline versions |
| `JATAYU_MAX_ITERATIONS` | Repair attempts (1–4) |
| `JATAYU_DASHBOARD_TOKEN` | Enables write actions on a deployed server |

The command is `jatayu`; the internal Python package is `unpinned`.

## Limitations

- Django is the only ecosystem with a verified upgrade path. Rails and Spring Boot are detected by Fleet but not yet upgradable.
- **Threat model:** verification proves the uploaded harness, patch archive and deletion manifest come back byte-for-byte unchanged, the exact source commit and framework version, and the frozen probe file's hash. It does not yet prove that the worktree could not be modified by the sandbox agent between steps; the results are not tamper-proof execution attestation.
- A passing result means the project's own tests, framework checks and the security probe passed. It is only as strong as the project's test suite.
- PR publication is disabled until the cloud verification and exact-patch approval flow is complete.
- Run artifacts are stored on local disk; container deployments need persistent storage.

## Built today

Jatayu was built during the Gemini 4 Argon SF Hackathon (Cerebral Valley × Google DeepMind) on October 25, 2026. All code in this repository was written that day; the history starts at commit `bc0c942`.

- **Upgrade pipeline:** packing, planning, long-decode migration, path-safe patch parsing with test-weakening checks, bounded repair loop (`src/unpinned/`)
- **Verification:** controller-owned sandbox harness, Files API artifact retrieval with integrity checks, raw-artifact parsers, evidence gate, patch review (`src/unpinned/verify/`, `artifacts/`, `evidence.py`, `review.py`)
- **Security fixture:** CVE-2026-87975 probe with benign control (`security_tests/`)
- **Ecosystem adapters:** Django, generic, Rails and Spring Boot roadmap (`src/unpinned/adapters/`)
- **Fleet:** end-of-life catalog, manifest detection, ranking, CLI and dashboard (`src/unpinned/fleet/`, `static/fleet.html`)
- **Server and deployment:** review API, Runs dashboard, write-token gate, Dockerfile, Cloud Run script, GitHub Action

The demo target [jatayu-demo-app](https://github.com/Jainparas99/jatayu-demo-app) was also written that day. Third-party projects are used only as inputs and are credited where results are reported.

## License

[MIT](LICENSE) © 2026 Paras Jain
