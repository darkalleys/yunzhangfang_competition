"""备份当前数据库，或将一个备份恢复到指定的新数据库。"""
import argparse
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tax_harness.maintenance import backup, restore
from tax_harness.store import DEFAULT_DB


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--db", type=Path, default=DEFAULT_DB)
    load = commands.add_parser("restore")
    load.add_argument("--snapshot", type=Path, required=True)
    load.add_argument("--to", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            print("备份已创建并验证：", backup(args.db))
        else:
            print("已恢复到新数据库：", restore(args.snapshot, args.to))
            print("当前业务库未覆盖，请通过 --db 选择恢复副本。")
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
