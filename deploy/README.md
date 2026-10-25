# Deploying Jatayu

The deployable app is `unpinned.server:app`: the upgrade-review API, the Approve flow and the
Fleet dashboard (`/fleet`). Upgrades themselves run in Google's Antigravity sandbox, so the
server is small: it needs no Docker-in-Docker and no build tools.

## Run locally

```bash
uv run uvicorn unpinned.server:app --port 8000     # http://127.0.0.1:8000/fleet
```

## Container (any host)

```bash
docker build -t jatayu .
docker run --rm -p 8080:8080 \
  -e GEMINI_API_KEY -e JATAYU_DASHBOARD_TOKEN \
  jatayu
```

## Google Cloud Run

`deploy/cloudrun.sh` deploys from source with secrets in Secret Manager and **no public
access** (`--no-allow-unauthenticated`). Use your own GCP project: the hackathon account only
has AI Studio access.

## Security model

- **Who can read:** whoever your platform lets reach the service. Keep it private (Cloud Run
  IAM / IAP, VPN). The page shows repo names and dependency versions.
- **Who can act:** every POST (fleet scan, approve) needs `Authorization: Bearer
  $JATAYU_DASHBOARD_TOKEN`. Without the variable the deployment is read-only.
- **What the server reads:** over HTTP, Fleet accepts only public `https://github.com/owner/repo`
  URLs, never local paths, and reads only dependency manifests.
- **Secrets:** come from the platform at runtime. The image never contains `.env`.
- **Storage:** `runs/` is local disk. On Cloud Run that's ephemeral; mount a volume or bucket
  if you need history.

## CI: the Jatayu GitHub Action

`action.yml` at the repo root fails a pull request (or just annotates it) when a dependency
manifest pins an end-of-life framework or runtime:

```yaml
# .github/workflows/jatayu.yml in the repo you want to guard
on: [pull_request]
jobs:
  eol:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Jainparas99/Jatayu@main
        with:
          fail-on: eol   # eol | expiring | never
```
