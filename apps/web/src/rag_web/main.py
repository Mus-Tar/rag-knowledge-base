import os
import sys
from pathlib import Path


def run() -> None:
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    app_path = Path(__file__).with_name("streamlit_app.py")
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address=0.0.0.0",
            "--server.headless=true",
            "--server.port=8501",
        ],
    )
