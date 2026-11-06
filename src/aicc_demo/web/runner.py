"""Local runner: extracts the courses YouTube won't serve to Google Cloud.

Runs on a machine on an ordinary network (`python runner.py`). It only makes
outgoing requests: it checks Firestore for queued courses, runs the normal
pipeline here, and files each PDF in the same bucket, so the cloud app sees
the row finish like any other. Stopping it is safe: an unfinished course
stays queued and starts over next time.
"""
import argparse
import os
import platform
import socket
import subprocess
import sys
import threading
import time

from google.auth.credentials import CredentialsWithQuotaProject
from google.auth.exceptions import DefaultCredentialsError

from aicc_demo.web.cloud_store import FirestoreProjectStore
from aicc_demo.web.pdf_store import GcsPdfStore
from aicc_demo.web.worker import run_extraction

POLL_SECONDS = 30
HEARTBEAT_SECONDS = 30


class GcloudCredentials(CredentialsWithQuotaProject):
    """Uses the `gcloud auth login` session, so no separate sign-in or key file is needed."""

    def __init__(self, quota_project_id: str | None = None):
        super().__init__()
        self._quota_project_id = quota_project_id

    def refresh(self, request) -> None:
        self.token = subprocess.run(
            ["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True
        ).stdout.strip()
        # Access tokens last about an hour; renew a bit early.
        from datetime import datetime, timedelta, timezone

        self.expiry = (datetime.now(timezone.utc) + timedelta(minutes=50)).replace(tzinfo=None)

    def with_quota_project(self, quota_project_id):
        return GcloudCredentials(quota_project_id)


def load_credentials(project: str):
    import google.auth

    try:
        return google.auth.default(quota_project_id=project)[0]
    except DefaultCredentialsError:
        return GcloudCredentials(project)


def process_next(store, pdf_store, scratch_dir: str, on_start=None) -> bool:
    """Extract the oldest queued course; False if the queue is empty."""
    entries = store.runner_entries()
    if not entries:
        return False
    entry = entries[0]
    if on_start:
        on_start(entry)
    try:
        run_extraction(store, pdf_store, entry["project_id"], entry["link_id"], entry.get("text_only", False), scratch_dir)
    except Exception as exc:  # e.g. the network dropped while recording the result
        print(f"Extraction failed for {entry['link_id']}: {exc}", file=sys.stderr)
        store.update_link(entry["project_id"], entry["link_id"], status="failed", progress="", error=str(exc)[:500])
    # Not reached on Ctrl+C, so an interrupted course stays queued and restarts.
    store.finish_runner_entry(entry["link_id"])
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract YouTube courses queued by the cloud app.")
    parser.add_argument("--project", default=os.environ.get("AICC_GCP_PROJECT"), required="AICC_GCP_PROJECT" not in os.environ,
                        help="Google Cloud project id")
    parser.add_argument("--bucket", help="PDF bucket (default: <project>-course-pdfs)")
    parser.add_argument("--once", action="store_true", help="work through the queue, then exit")
    args = parser.parse_args(argv)

    from google.cloud import firestore, storage

    credentials = load_credentials(args.project)
    store = FirestoreProjectStore(client=firestore.Client(project=args.project, credentials=credentials))
    pdf_store = GcsPdfStore(args.bucket or f"{args.project}-course-pdfs",
                            client=storage.Client(project=args.project, credentials=credentials))
    host = socket.gethostname() or platform.node()
    scratch_dir = os.path.join("data", "runner", "pdf")
    busy = {"title": None}

    def heartbeat() -> None:
        while True:
            try:
                store.runner_heartbeat(host, busy["title"])
            except Exception as exc:
                print(f"Heartbeat failed: {exc}", file=sys.stderr)
            time.sleep(HEARTBEAT_SECONDS)

    threading.Thread(target=heartbeat, daemon=True).start()
    print(f"Runner on {host} watching project {args.project} (Ctrl+C to stop)", flush=True)

    def started(entry: dict) -> None:
        busy["title"] = entry["link_id"]
        print(f"Extracting {entry['link_id']} from project {entry['project_id']}", flush=True)

    try:
        while True:
            worked = process_next(store, pdf_store, scratch_dir, started)
            busy["title"] = None
            if worked:
                print("Finished; checking for more", flush=True)
            elif args.once:
                return 0
            else:
                time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("Stopped. Any unfinished course stays queued.", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
