#!/usr/bin/env bash
# Give the cloud job a YouTube login, or refresh an expired one.
#
#   PROJECT_ID=my-project REGION=us-east1 ./deploy/set-youtube-cookies.sh youtube-cookies.txt
#
# FILE is a Netscape-format cookies.txt exported from a signed-in YouTube
# session of a separate, throwaway Google account. Only youtube.com and
# google.com lines are uploaded. Takes effect on the next Extract; nothing
# needs redeploying. Delete FILE afterwards: it works like a password.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
FILE="${1:?usage: set-youtube-cookies.sh COOKIES_FILE}"
REGION="${REGION:-us-east1}"
JOB="${JOB:-course-to-pdf-extract}"
COOKIE_SECRET="${COOKIE_SECRET:-youtube-cookies}"
SA="${SA_NAME:-course-to-pdf}@${PROJECT_ID}.iam.gserviceaccount.com"
COOKIE_FILE="/secrets/youtube/cookies.txt"

FILTERED="$(mktemp)"
trap 'rm -f "$FILTERED"' EXIT
{ echo "# Netscape HTTP Cookie File"
  grep -E '^(#HttpOnly_)?\.?([a-z0-9-]+\.)*(youtube|google)\.com[[:space:]]' "$FILE" || true
} > "$FILTERED"
COUNT="$(grep -c 'youtube\.com' "$FILTERED" || true)"
if [ "$COUNT" -eq 0 ]; then
  echo "No youtube.com cookies in $FILE. Export it while signed in to YouTube." >&2
  exit 1
fi
echo "Uploading $(($(wc -l < "$FILTERED") - 1)) cookie lines ($COUNT for youtube.com)."

if gcloud secrets describe "$COOKIE_SECRET" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets versions add "$COOKIE_SECRET" --project "$PROJECT_ID" --data-file="$FILTERED"
else
  gcloud secrets create "$COOKIE_SECRET" --project "$PROJECT_ID" --data-file="$FILTERED" --replication-policy automatic
fi
gcloud secrets add-iam-policy-binding "$COOKIE_SECRET" --project "$PROJECT_ID" \
  --member "serviceAccount:${SA}" --role roles/secretmanager.secretAccessor >/dev/null
gcloud run jobs update "$JOB" --project "$PROJECT_ID" --region "$REGION" \
  --update-env-vars "AICC_YT_COOKIES_FILE=${COOKIE_FILE}" \
  --update-secrets "${COOKIE_FILE}=${COOKIE_SECRET}:latest"
echo "Done. Now delete $FILE."
