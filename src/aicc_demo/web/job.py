"""Entry point of the Cloud Run extraction job: `python -m aicc_demo.web.job`.

The web service starts one execution per Extract click with
AICC_PROJECT_ID, AICC_LINK_IDS (comma-separated) and AICC_TEXT_ONLY; Cloud
Run runs one task per link and sets CLOUD_RUN_TASK_INDEX in each, so task
N extracts the N-th link.
"""
import os
import sys

from aicc_demo.web.cloud_store import FirestoreProjectStore
from aicc_demo.web.pdf_store import GcsPdfStore
from aicc_demo.web.worker import run_extraction

# Cloud Run's only writable disk is in memory (counts against the task's
# memory limit); work under /tmp so downloads and frames land there.
WORK_DIR = "/tmp/aicc"


def main(store=None, pdf_store=None) -> int:
    link_ids = [i for i in os.environ.get("AICC_LINK_IDS", "").split(",") if i]
    index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    if index >= len(link_ids):
        print(f"task {index}: nothing to do ({len(link_ids)} links)", file=sys.stderr)
        return 0
    project_id = os.environ["AICC_PROJECT_ID"]
    text_only = os.environ.get("AICC_TEXT_ONLY") == "1"
    store = store or FirestoreProjectStore()
    pdf_store = pdf_store or GcsPdfStore(os.environ["AICC_BUCKET"])
    os.makedirs(WORK_DIR, exist_ok=True)
    os.chdir(WORK_DIR)
    print(f"task {index}: project {project_id} link {link_ids[index]} text_only={text_only}", file=sys.stderr)
    run_extraction(store, pdf_store, project_id, link_ids[index], text_only, scratch_dir=os.path.join(WORK_DIR, "pdf"))
    # The outcome (done/failed) is on the row; exit 0 so Cloud Run doesn't retry.
    return 0


if __name__ == "__main__":
    sys.exit(main())
