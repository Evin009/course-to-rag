#!/usr/bin/env bash
# Deploy Course to PDF into YOUR Google Cloud project.
#
#   PROJECT_ID=my-project REGION=us-east1 ./deploy/gcp.sh
#
# Creates (if missing): APIs, an Artifact Registry repo, a Cloud Storage
# bucket, a Firestore database, the Canvas token secret, a service account,
# then builds the image with Cloud Build and deploys:
#   - Cloud Run job      course-to-pdf-extract  (one task per course)
#   - Cloud Run service  course-to-pdf          (the web UI, private)
# Safe to re-run: existing resources are kept, the image and services are updated.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID, e.g. PROJECT_ID=my-project}"
REGION="${REGION:-us-east1}"
BUCKET="${BUCKET:-${PROJECT_ID}-course-pdfs}"
SERVICE="${SERVICE:-course-to-pdf}"
JOB="${JOB:-course-to-pdf-extract}"
REPO="${REPO:-course-to-pdf}"
SA_NAME="${SA_NAME:-course-to-pdf}"
SECRET="${SECRET:-canvas-token}"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/app:$(date +%Y%m%d-%H%M%S)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

step() { printf '\n==> %s\n' "$*"; }

step "Project ${PROJECT_ID}, region ${REGION}"
gcloud config set project "$PROJECT_ID" >/dev/null

step "Enabling APIs (first run takes a minute)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com storage.googleapis.com iam.googleapis.com

step "Artifact Registry repo ${REPO}"
gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION"

step "Bucket gs://${BUCKET}"
gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 \
  || gcloud storage buckets create "gs://${BUCKET}" --location "$REGION" --uniform-bucket-level-access

step "Firestore (native mode)"
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 \
  || gcloud firestore databases create --location "$REGION" --type firestore-native

step "Secret ${SECRET} (Canvas token from .env)"
TOKEN="$(grep -E '^CANVAS_TOKEN=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"' ')"
if ! gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
  [ -n "$TOKEN" ] || { echo "No CANVAS_TOKEN in .env"; exit 1; }
  printf '%s' "$TOKEN" | gcloud secrets create "$SECRET" --data-file=- --replication-policy automatic
else
  echo "exists (to update: printf '%s' NEW_TOKEN | gcloud secrets versions add $SECRET --data-file=-)"
fi

step "Service account ${SA}"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA_NAME" --display-name "Course to PDF"
for role in roles/datastore.user roles/run.developer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${SA}" --role "$role" --condition None >/dev/null
done
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member "serviceAccount:${SA}" --role roles/storage.objectAdmin >/dev/null
gcloud secrets add-iam-policy-binding "$SECRET" --member "serviceAccount:${SA}" --role roles/secretmanager.secretAccessor >/dev/null
# The web service starts job executions that run as this same account.
gcloud iam service-accounts add-iam-policy-binding "$SA" --member "serviceAccount:${SA}" --role roles/iam.serviceAccountUser >/dev/null
# Cloud Build also runs as this account: it reads the uploaded source and pushes the image.
gcloud artifacts repositories add-iam-policy-binding "$REPO" --location "$REGION" \
  --member "serviceAccount:${SA}" --role roles/artifactregistry.writer >/dev/null
gcloud storage buckets describe "gs://${PROJECT_ID}_cloudbuild" >/dev/null 2>&1 \
  || gcloud storage buckets create "gs://${PROJECT_ID}_cloudbuild" --location US --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding "gs://${PROJECT_ID}_cloudbuild" \
  --member "serviceAccount:${SA}" --role roles/storage.objectViewer >/dev/null

step "Building ${IMAGE} with Cloud Build (~5-8 min the first time)"
gcloud builds submit "$ROOT" --config "$ROOT/deploy/cloudbuild.yaml" --substitutions "_IMAGE=${IMAGE}" \
  --service-account "projects/${PROJECT_ID}/serviceAccounts/${SA}" --region "$REGION"

# Optional YouTube login for the job; see deploy/set-youtube-cookies.sh.
COOKIE_SECRET="${COOKIE_SECRET:-youtube-cookies}"
COOKIE_FILE="/secrets/youtube/cookies.txt"
JOB_EXTRA_ENV=""
JOB_EXTRA_SECRETS=""
if gcloud secrets describe "$COOKIE_SECRET" >/dev/null 2>&1; then
  JOB_EXTRA_ENV=",AICC_YT_COOKIES_FILE=${COOKIE_FILE}"
  JOB_EXTRA_SECRETS=",${COOKIE_FILE}=${COOKIE_SECRET}:latest"
fi

ENV_VARS="AICC_MODE=cloud,AICC_GCP_PROJECT=${PROJECT_ID},AICC_REGION=${REGION},AICC_BUCKET=${BUCKET},AICC_JOB_NAME=${JOB}"

step "Cloud Run job ${JOB}"
# 4 CPU / 8 GiB: downloads and frames live in the in-memory /tmp; Whisper is CPU-bound.
gcloud run jobs deploy "$JOB" --image "$IMAGE" --region "$REGION" --service-account "$SA" \
  --command python --args=-m,aicc_demo.web.job \
  --cpu 4 --memory 8Gi --task-timeout 3600 --max-retries 0 --parallelism 0 \
  --set-env-vars "${ENV_VARS}${JOB_EXTRA_ENV}" --set-secrets "CANVAS_TOKEN=${SECRET}:latest${JOB_EXTRA_SECRETS}"

step "Cloud Run service ${SERVICE} (private)"
gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" --service-account "$SA" \
  --no-allow-unauthenticated --cpu 1 --memory 1Gi --timeout 300 --max-instances 2 \
  --set-env-vars "$ENV_VARS" --set-secrets "CANVAS_TOKEN=${SECRET}:latest"

step "Done"
cat <<MSG
Open the app (private; uses your gcloud login):
  gcloud run services proxy ${SERVICE} --region ${REGION} --port 8090
  -> http://127.0.0.1:8090  (127.0.0.1, not localhost: avoids oversized-cookie errors)

PDFs: gs://${BUCKET}/<project-name>/NN-<course-title>.pdf
Logs: gcloud run jobs executions list --job ${JOB} --region ${REGION}
MSG
