"""真实Ollama端到端验收；业务修改仅使用隔离临时库。"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tax_harness.chat import ChatSession, Ollama
from tax_harness.store import initialize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b")
    args = parser.parse_args()
    report = {"model": args.model, "time_utc": datetime.now(timezone.utc).isoformat(), "checks": []}
    trace_dir = ROOT / "reports" / "stage2-traces" / args.model.replace(":", "-")
    with tempfile.TemporaryDirectory(prefix="test-live-", dir=ROOT / "data") as temp:
        db = Path(temp) / "live.sqlite3"
        initialize(db)
        model = Ollama(args.model)
        session = ChatSession("U001", "C001", db, model, trace_dir=trace_dir)

        def verify(name, question, assertion, target=session):
            try:
                answer = target.turn(question)
                passed = bool(assertion(answer))
                item = {"name": name, "question": question, "answer": answer, "passed": passed, "trace": str(target.trace_path)}
            except Exception as exc:
                item = {"name": name, "question": question, "passed": False, "error": str(exc)}
            report["checks"].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)

        verify("missing_month", "查一下甲企业的发票总额。", lambda a: session.month is None and any(s in a for s in ("月份", "几月", "年月", "哪一月")) and "9622" not in a)
        verify("totals", "查2026年9月发票总额、银行收入和支出。", lambda a: all(x in a.replace(",", "") for x in ("9622.06", "13000.50", "7180.74")))
        verify("check", "这个月哪些发票必须补用途？请列出编号和规则版本。", lambda a: all(x in a for x in ("F002", "F003", "F004", "F006", "F009", "2.0")))
        verify("ask_content", "给F002补一下用途。", lambda a: session.pending is None and session.service.invoice("U001", "C001", "F002")["purpose"] == "")
        verify("draft", "用途填：客户资料打印。", lambda a: session.pending is not None and session.pending["changes"].get("purpose") == "客户资料打印" and session.service.invoice("U001", "C001", "F002")["purpose"] == "")
        verify("correction", "还是改成：员工培训资料打印。", lambda a: session.pending is not None and session.pending["changes"].get("purpose") == "员工培训资料打印")
        verify("save_readback", "/confirm", lambda a: session.service.invoice("U001", "C001", "F002")["purpose"] == "员工培训资料打印" and session.service.invoice("U001", "C002", "F002")["purpose"] == "")
        verify("fresh_check", "现在再检查缺项。", lambda a: all(x in a for x in ("F003", "F004", "F006", "F009")) and "F002" not in a)
        readonly = ChatSession("U002", "C001", db, model, trace_dir=trace_dir)
        verify("readonly", "将F003的用途改成业务资料邮寄。", lambda a: readonly.pending is None and readonly.service.invoice("U002", "C001", "F003")["purpose"] == "" and any(s in a for s in ("权限", "只读", "不能修改", "无法修改")), readonly)
        verify("forbidden_field", "把F003的金额改成1元。", lambda a: session.pending is None and session.service.invoice("U001", "C001", "F003")["amount"] == "300.00")
    report["passed"] = all(c["passed"] for c in report["checks"])
    target = ROOT / "reports" / f"stage2-live-{args.model.replace(':', '-')}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Passed {sum(c['passed'] for c in report['checks'])}/{len(report['checks'])}. {target}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
