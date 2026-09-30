import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from .service import TimeService
from .store import Store, default_db


def show(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="TimeReact：AI 时间感知工具")
    parser.add_argument("--db", type=Path, default=default_db(), help="本地记录文件")
    parser.add_argument("--session", default="cli", help="会话标识，默认 cli")
    commands = parser.add_subparsers(dest="command", required=True)
    now = commands.add_parser("now", help="当前时间与距上次观察的时长")
    now.add_argument("--timezone", default="Asia/Shanghai")
    start = commands.add_parser("start", help="开始计时")
    start.add_argument("--label", default="任务")
    group = start.add_mutually_exclusive_group()
    group.add_argument("--seconds", type=float)
    group.add_argument("--deadline")
    for name, help_text in (("status", "查询计时器"), ("cancel", "取消计时器")):
        item = commands.add_parser(name, help=help_text)
        item.add_argument("timer_id")
    commands.add_parser("list", help="本会话最近的计时器")
    commands.add_parser("demo", help="演示一个两秒预算的任务，不保存演示记录")
    commands.add_parser("config", help="生成当前项目的 Codex MCP 配置片段")
    args = parser.parse_args()
    try:
        if args.command == "config":
            root = Path(__file__).resolve().parents[2]
            executable = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            print("[mcp_servers.timereact]")
            print("command = " + json.dumps(str(executable if executable.exists() else Path(sys.executable))))
            print("args = " + json.dumps([str(root / "scripts/run_server.py")]))
            print("\n[mcp_servers.timereact.env]")
            print("TIMEREACT_DB = " + json.dumps(str(args.db.expanduser().resolve())))
            return
        if args.command == "demo":
            with tempfile.TemporaryDirectory(prefix="timereact-demo-") as folder:
                service = TimeService(Store(Path(folder) / "state.sqlite3"))
                initial = service.start_timer("demo", "演示任务", 2)
                print("任务开始：预算 2 秒。")
                time.sleep(0.5)
                middle = service.get_timer("demo", initial["timer_id"])
                print(f"阶段检查：已用 {middle['elapsed_seconds']} 秒，剩余 {middle['remaining_seconds']} 秒。")
                time.sleep(1.6)
                end = service.get_timer("demo", initial["timer_id"])
                print(f"再次检查：状态 {end['status']}，超时 {end['overdue_seconds']} 秒。")
                print("这是工具计时演示；AI 是否据此调整任务，需要接入后的行为验证。")
            return
        service = TimeService(Store(args.db))
        if args.command == "now":
            result = service.get_time_context(args.session, args.timezone)
        elif args.command == "start":
            result = service.start_timer(args.session, args.label, args.seconds, args.deadline)
        elif args.command == "status":
            result = service.get_timer(args.session, args.timer_id)
        elif args.command == "cancel":
            result = service.cancel_timer(args.session, args.timer_id)
        else:
            result = service.list_timers(args.session)
        show(result)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"错误：{exc}\n")


if __name__ == "__main__":
    main()
