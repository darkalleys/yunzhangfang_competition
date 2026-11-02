"""以独立进程运行真实 CLI，生成可核对的第一阶段验收记录。"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(db, *args, expected=0):
    proc = subprocess.run([sys.executable, "-X", "utf8", "-m", "tax_harness", "--db", str(db), "--json", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
    if proc.returncode != expected:
        raise AssertionError(f"CLI退出码异常：{args}\n{proc.stdout}\n{proc.stderr}")
    payload = json.loads(proc.stdout if expected == 0 else proc.stderr)
    assert payload["ok"] == (expected == 0)
    return payload["data"] if expected == 0 else payload["error"]


def main():
    report = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version.split()[0], "checks": []}
    with tempfile.TemporaryDirectory(prefix="test-smoke-", dir=ROOT / "data") as temp:
        db = Path(temp) / "smoke.sqlite3"
        imported = run(db, "init")
        assert imported["invoices"] == 40 and imported["bank_records"] == 48
        report["checks"].append({"name": "import", "invoices": 40, "bank_records": 48, "rules": imported["rules"]})
        for company, month, invoice, expense, income in (
            ("C001", "2026-08", "9046.35", "5720.99", "14850.75"),
            ("C001", "2026-09", "9622.06", "7180.74", "13000.50"),
            ("C002", "2026-08", "13667.05", "9341.10", "18800.25"),
            ("C002", "2026-09", "12667.24", "8087.24", "13700.75"),
        ):
            result = run(db, "totals", "--user", "U001", "--company", company, "--month", month)
            assert (result["invoice_total"], result["bank_expense"], result["bank_income"]) == (invoice, expense, income)
            report["checks"].append({"name": "totals", "result": result})
        for company, expected in (("C001", ["F002", "F003", "F004", "F006", "F009"]), ("C002", ["F002", "F005", "F006"])):
            result = run(db, "check", "--user", "U001", "--company", company, "--month", "2026-09")
            assert [r["invoice_id"] for r in result["missing"]] == expected
            report["checks"].append({"name": "purpose_check", "result": result})
        invoice_args = ("--user", "U001", "--company", "C001", "--invoice", "F002")
        before = run(db, "invoice", *invoice_args)
        saved = run(db, "update", *invoice_args, "--purpose", "命令行自测用途", "--operation-id", "smoke-op-1")
        readback = run(db, "invoice", *invoice_args)
        assert before["purpose"] == "" and readback["purpose"] == "命令行自测用途"
        assert saved["readback"] == readback and saved["matches_requested"]
        other = run(db, "invoice", "--user", "U001", "--company", "C002", "--invoice", "F002")
        assert other["purpose"] == ""
        assert run(db, "check", "--user", "U001", "--company", "C001", "--month", "2026-09")["missing_count"] == 4
        replay = run(db, "update", *invoice_args, "--purpose", "命令行自测用途", "--operation-id", "smoke-op-1")
        assert replay["replayed"]
        report["checks"].append({"name": "save_readback_isolation_and_replay", "before": before, "saved": saved, "other_company_invoice": other})
        for args in (
            ("totals", "--user", "U002", "--company", "C002", "--month", "2026-09"),
            ("update", "--user", "U002", "--company", "C001", "--invoice", "F002", "--purpose", "不应写入"),
        ):
            error = run(db, *args, expected=1)
            assert error["code"] == "permission_denied"
            report["checks"].append({"name": "permission_denied", "error": error})
        assert not run(db, "init")["created"]
        assert run(db, "invoice", *invoice_args)["purpose"] == "命令行自测用途"
        menu = subprocess.run([sys.executable, "-X", "utf8", "-m", "tax_harness", "--db", str(db), "menu"], cwd=ROOT, input="2\n3\n0\n", capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert menu.returncode == 0 and "9622.06" in menu.stdout and "4 张必须补充用途" in menu.stdout
        report["checks"].append({"name": "interactive_menu", "output": menu.stdout})
        report["checks"].append({"name": "reinitialize_preserves_current_data", "passed": True})
    report["passed"] = True
    report["test_data_isolated"] = True
    target = ROOT / "reports" / "stage1-smoke.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CLI及菜单验收通过，{len(report['checks'])}项检查。记录：{target}")


if __name__ == "__main__":
    main()
