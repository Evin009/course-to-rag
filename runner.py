"""Start the local runner, which extracts YouTube courses for the cloud app.

    python runner.py --project <google-cloud-project-id>

Keep it running while courses are queued; on a Mac, `caffeinate -i python runner.py ...`
stops the machine sleeping. Needs ffmpeg, tesseract and deno installed, and `gcloud auth login`.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# See extract.py: the editable install's .pth can be skipped inside iCloud Drive.
sys.path.insert(0, str(ROOT / "src"))
# The pipeline writes working files to data/<course>; keep them in the project.
os.chdir(ROOT)

from aicc_demo.web.runner import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
