"""Write configuration snippets without changing existing Codex settings."""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


def generate(root: Path, output: Path) -> tuple[Path, Path]:
    root = root.resolve()
    executable = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not executable.is_file():
        raise ValueError("请先在项目根目录创建 .venv 并安装依赖")
    if sys.platform == "win32":
        command = subprocess.list2cmdline([str(executable), str(root / "scripts/conversation_hook.py")])
    else:
        command = shlex.join([str(executable), str(root / "scripts/conversation_hook.py")])
    data = root / ".timereact/state.sqlite3"
    config = "\n".join([
        "[mcp_servers.timereact]",
        "command = " + json.dumps(str(executable)),
        "args = " + json.dumps([str(root / "scripts/run_server.py")]),
        "", "[mcp_servers.timereact.env]",
        "TIMEREACT_DB = " + json.dumps(str(data)), "",
    ])
    hooks = {"description": "TimeReact：对话时间锚点；请在 Codex /hooks 中审核并信任。", "hooks": {}}
    for event in ("SessionStart", "UserPromptSubmit", "Stop"):
        hooks["hooks"][event] = [{"hooks": [{"type": "command", "command": command,
                                           "timeout": 5, "additionalContextLimit": 2000}]}]
    output.mkdir(parents=True, exist_ok=True)
    mcp_path, hook_path = output / "codex-mcp.toml", output / "codex-hooks.json"
    mcp_path.write_text(config, encoding="utf-8")
    hook_path.write_text(json.dumps(hooks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return mcp_path, hook_path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="生成本机 Codex 配置片段，不修改现有 Codex 设置")
    parser.add_argument("--output", type=Path, default=root / ".timereact/config")
    args = parser.parse_args()
    try:
        for path in generate(root, args.output.expanduser().resolve()):
            print(path)
        print("请合并配置片段并安装 skill，再在 Codex /hooks 中信任三个事件。")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"错误：{exc}\n")


if __name__ == "__main__":
    main()
