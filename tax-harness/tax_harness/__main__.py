import argparse
import json
from pathlib import Path
import sqlite3
import sys
from zipfile import BadZipFile

from .service import Service
from .store import BusinessError, DEFAULT_DB, DEFAULT_SOURCE, initialize


def show(kind, result, as_json=False):
    if as_json:
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, indent=2))
        return
    if kind == "init":
        print(result.get("message", "初始化成功：2家企业、2名用户、40张发票、48条流水、5条规则记录。"))
        print("数据库：", result["database"])
    elif kind == "totals":
        print(f"{result['company_id']} / {result['month']}")
        print(f"发票：{result['invoice_count']}张，价税合计 {result['invoice_total']} 元")
        print(f"银行：{result['bank_count']}条，收入 {result['bank_income']} 元，支出 {result['bank_expense']} 元")
        if result["no_records"]:
            print("查询成功，该企业此月没有业务记录。")
        print(f"依据：《{result['rule']['name']}》{result['rule']['version']}版")
    elif kind == "check":
        print(f"{result['company_id']} / {result['month']}：检查 {result['invoice_count']} 张发票，{result['missing_count']} 张必须补充用途。")
        for row in result["missing"]:
            print(f"  {row['invoice_id']}  {row['amount']} 元  {row['item']}")
        print(f"依据：《{result['rule']['name']}》{result['rule']['version']}版")
    elif kind == "invoice":
        labels = {"company_id": "企业", "invoice_id": "发票编号", "invoice_date": "日期", "seller": "销售方", "item": "票面项目", "amount": "金额（元）", "purpose": "用途", "remark": "备注"}
        for key, value in result.items():
            print(f"{labels.get(key, key)}：{value if value else '（空）'}")
    elif kind == "update":
        if result["replayed"]:
            print("该操作此前已处理，本次没有重复写入。")
        elif result["changed"]:
            print("已保存，并通过新数据库连接重新查询核对。")
        else:
            print("当前内容与请求一致，字段没有变化；已回读核对。")
        if not result["matches_requested"]:
            print("注意：当前内容与该历史请求不同，可能在之后被更正；以下为当前保存值。")
        print("操作编号：", result["operation_id"])
        show("invoice", result["readback"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def report_error(exc, as_json=False):
    code = exc.code if isinstance(exc, BusinessError) else "storage_or_input_error"
    if as_json:
        print(json.dumps({"ok": False, "error": {"code": code, "message": str(exc)}}, ensure_ascii=False), file=sys.stderr)
    else:
        print(f"操作失败 [{code}]：{exc}", file=sys.stderr)


def menu(db):
    show("init", initialize(db))
    print("\n财税 Harness 第一阶段：业务工具演示（尚未接入模型）")
    user, company, month = "U001", "C001", "2026-09"
    while True:
        print(f"\n当前身份 {user} | 企业 {company} | 月份 {month}")
        print("1 切换身份/企业/月  2 查金额  3 查用途缺项  4 查单张发票\n5 修改用途/备注  6 查修改记录  0 退出")
        choice = input("选择：").strip()
        service = Service(db)
        try:
            if choice == "0":
                return
            if choice == "1":
                new_user = input(f"用户 U001/U002 [{user}]：").strip() or user
                new_company = input(f"企业 C001/C002 [{company}]：").strip() or company
                new_month = input(f"月份 YYYY-MM [{month}]：").strip() or month
                # 用实际授权查询校验上下文；失败时保留原有上下文。
                service.totals(new_user, new_company, new_month)
                user, company, month = new_user, new_company, new_month
            elif choice == "2":
                show("totals", service.totals(user, company, month))
            elif choice == "3":
                show("check", service.check(user, company, month))
            elif choice == "4":
                show("invoice", service.invoice(user, company, input("发票编号：").strip()))
            elif choice == "5":
                invoice_id = input("发票编号：").strip()
                field = input("字段：1 用途 / 2 备注：").strip()
                if field not in ("1", "2"):
                    raise BusinessError("invalid_field", "请选择1或2。")
                value = input("填写内容（直接回车会清空该字段）：")
                show("update", service.update(user, company, invoice_id, {"purpose" if field == "1" else "remark": value}))
            elif choice == "6":
                show("audit", service.audit(user, company))
            else:
                print("请输入菜单中的数字。")
        except (BusinessError, sqlite3.Error, ValueError, OSError) as exc:
            report_error(exc)


def parser():
    p = argparse.ArgumentParser(description="财税 Harness：本地业务工具与Ollama对话")
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite数据库路径，默认data/business.sqlite3")
    p.add_argument("--json", action="store_true", help="输出结构化JSON（错误输出至stderr）")
    sub = p.add_subparsers(dest="command")
    init = sub.add_parser("init", help="导入原始材料；已有数据库不会覆盖")
    init.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    sub.add_parser("menu", help="打开交互菜单")
    chat = sub.add_parser("chat", help="使用Ollama进行自然语言对话")
    chat.add_argument("--user", required=True)
    chat.add_argument("--company", required=True)
    chat.add_argument("--month", default=None)
    chat.add_argument("--model", default="qwen3:8b")
    for name, help_text in (("totals", "查询月度金额"), ("check", "检查九月用途缺项"), ("invoice", "查询单张发票"), ("update", "修改用途或备注并回读"), ("audit", "查看本企业最近100次保存记录")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--user", required=True, help="演示身份 U001/U002")
        cmd.add_argument("--company", required=True, help="企业 C001/C002")
        if name in ("totals", "check"):
            cmd.add_argument("--month", required=True, help="YYYY-MM，不默认当前月份")
        if name in ("invoice", "update"):
            cmd.add_argument("--invoice", required=True, dest="invoice_id")
        if name == "update":
            cmd.add_argument("--purpose", default=None, help="用途，传空字符串表示清空")
            cmd.add_argument("--remark", default=None, help="备注，传空字符串表示清空")
            cmd.add_argument("--operation-id", default=None, help="可选幂等操作编号，相同编号不重复保存")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    command = args.command or "menu"
    try:
        service = Service(args.db)
        if command == "chat":
            from .chat import chat_cli
            chat_cli(args)
            return 0
        if command == "menu":
            menu(args.db)
            return 0
        if command == "init":
            result = initialize(args.db, args.source)
        elif command in ("totals", "check"):
            result = getattr(service, command)(args.user, args.company, args.month)
        elif command == "invoice":
            result = service.invoice(args.user, args.company, args.invoice_id)
        elif command == "update":
            changes = {key: getattr(args, key) for key in ("purpose", "remark") if getattr(args, key) is not None}
            result = service.update(args.user, args.company, args.invoice_id, changes, args.operation_id)
        else:
            result = service.audit(args.user, args.company)
        show(command, result, args.json)
        return 0
    except (BusinessError, sqlite3.Error, ValueError, OSError, BadZipFile, KeyError) as exc:
        report_error(exc, args.json)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\n已退出。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
