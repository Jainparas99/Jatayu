#!/usr/bin/env bash
# Deploy Jatayu to Cloud Run from source, private by default.
# Prereqs (once): gcloud auth login; gcloud config set project <your-project>;
#   printf %s "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
#   openssl rand -hex 24 | gcloud secrets create jatayu-dashboard-token --data-file=-
set -euo pipefail
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-jatayu}"

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --no-allow-unauthenticated \
  --memory 1Gi \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,JATAYU_DASHBOARD_TOKEN=jatayu-dashboard-token:latest"

echo "Open it with:  gcloud run services proxy $SERVICE --region $REGION  → http://localhost:8080/fleet"
