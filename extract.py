"""Turn an Articulate Rise course link into labeled course text and one AICC-ready PDF.

    python extract.py https://share.articulate.com/<id> [--interval 10] [--max-frames 15] [--text-only]
"""
import sys
from pathlib import Path

# The editable install's .pth can be ignored (iCloud Drive marks it hidden
# and Python 3.13 skips hidden .pth files), so put src/ on the path directly.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aicc_demo.cli import main

if __name__ == "__main__":
    sys.exit(main())
