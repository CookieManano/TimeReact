"""Start the server with the local environment or an installed MCP SDK."""

import importlib.util
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
venv_python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
if importlib.util.find_spec("mcp") is None:
    if venv_python.exists() and Path(sys.prefix).resolve() != (root / ".venv").resolve():
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.exit("缺少 MCP SDK。请先在项目虚拟环境中安装 requirements-lock.txt。")

data_root = Path(os.environ.get("PLUGIN_DATA", str(root / ".timereact")))
os.environ.setdefault("TIMEREACT_DB", str(data_root / "state.sqlite3"))
sys.path.insert(0, str(root / "src"))

from timereact.server import main

if __name__ == "__main__":
    main()
