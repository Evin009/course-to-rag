"""Start the Course-to-PDF web UI on http://127.0.0.1:8000

    python webapp.py            # serves the built frontend + API
    python webapp.py --no-open  # don't open a browser tab
"""
import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# See extract.py: the editable install's .pth can be skipped inside iCloud Drive.
sys.path.insert(0, str(ROOT / "src"))
# The pipeline writes working files to data/<course>; keep them in the project.
os.chdir(ROOT)

import uvicorn  # noqa: E402

from aicc_demo.web.app import create_app  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"Course to PDF running at {url}  (Ctrl+C to stop)")
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
