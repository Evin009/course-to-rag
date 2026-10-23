"""List the Articulate Rise courses linked in a Canvas course, and optionally extract them.

    python canvas.py https://usflearn.instructure.com/courses/<id> [--extract all|1,3,5-7]

Needs CANVAS_TOKEN (Canvas -> Account -> Settings -> + New Access Token) in .env or the environment.
"""
import sys
from pathlib import Path

# See extract.py: the editable install's .pth can be skipped inside iCloud Drive.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aicc_demo.canvas_cli import main

if __name__ == "__main__":
    sys.exit(main())
