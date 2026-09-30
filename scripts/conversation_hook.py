"""Run conversation hooks with the standard library, without starting the MCP server."""

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data_root = Path(os.environ.get("PLUGIN_DATA", str(root / ".timereact")))
os.environ.setdefault("TIMEREACT_DB", str(data_root / "state.sqlite3"))
sys.path.insert(0, str(root / "src"))

from timereact.hooks import main

if __name__ == "__main__":
    main()
