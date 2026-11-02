"""后续可直接接入模型的业务工具，权限始终由本层校验。"""

from datetime import date, datetime, timezone
import json
import re
from uuid import uuid4

from .store import BusinessError, DEFAULT_DB, connect


def money(value):
    return f"{value // 100}.{value % 100:02d}"


def month_bounds(month):
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-\d{2}", month):
        raise BusinessError("invalid_month", "请明确提供月份，格式为 YYYY-MM，例如 2026-09。")
    try:
        start = date.fromisoformat(month + "-01")
        end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    except ValueError as exc:
        raise BusinessError("invalid_month", "月份无效。") from exc
    return start.isoformat(), end.isoformat()


def authorize(con, user, company, write=False):
    row = con.execute("SELECT can_read,can_write FROM permissions WHERE user_id=? AND company_id=?", (user, company)).fetchone()
    if row is None or not row["can_read"]:
        raise BusinessError("permission_denied", "当前用户无权访问该企业。")
    if write and not row["can_write"]:
        raise BusinessError("permission_denied", "当前用户仅有查看权限，不能修改发票。")


def public_invoice(row):
    result = dict(row)
    result["amount"] = money(result.pop("amount_cents"))
    return result


def select_rule(con, company, business_date, kinds):
    marks = ",".join("?" for _ in kinds)
    rows = con.execute(f"SELECT * FROM rules WHERE (company_id=? OR company_id IS NULL) AND status='active' AND effective_date<=? AND kind IN ({marks}) ORDER BY effective_date DESC", (company, business_date, *kinds)).fetchall()
    if not rows:
        raise BusinessError("rule_missing", "没有可用的适用规则，无法完成本次检查。")
    if len(rows) > 1 and rows[0]["effective_date"] == rows[1]["effective_date"]:
        raise BusinessError("rule_conflict", "存在同日生效的冲突规则，需要先处理规则配置。")
    return dict(rows[0])


class Service:
    def __init__(self, db=DEFAULT_DB):
        self.db = db

    def totals(self, user, company, month):
        start, end = month_bounds(month)
        with connect(self.db) as con:
            authorize(con, user, company)
            invoice = con.execute("SELECT COUNT(*) AS n,COALESCE(SUM(amount_cents),0) AS total FROM invoices WHERE company_id=? AND invoice_date>=? AND invoice_date<?", (company, start, end)).fetchone()
            bank = con.execute("SELECT direction,COUNT(*) AS n,SUM(amount_cents) AS total FROM bank_records WHERE company_id=? AND transaction_date>=? AND transaction_date<? GROUP BY direction", (company, start, end)).fetchall()
            grouped = {r["direction"]: r for r in bank}
            rule = select_rule(con, company, start, ("amounts",))
        return {"company_id": company, "month": month, "invoice_count": invoice["n"], "bank_count": sum(r["n"] for r in bank), "invoice_total": money(invoice["total"]), "bank_income": money(grouped["收入"]["total"] if "收入" in grouped else 0), "bank_expense": money(grouped["支出"]["total"] if "支出" in grouped else 0), "no_records": invoice["n"] == 0 and not bank, "rule": rule}

    def invoice(self, user, company, invoice_id):
        with connect(self.db) as con:
            authorize(con, user, company)
            row = con.execute("SELECT * FROM invoices WHERE company_id=? AND invoice_id=?", (company, invoice_id)).fetchone()
            if row is None:
                raise BusinessError("not_found", "该企业下没有找到指定发票。")
            return public_invoice(row)

    def check(self, user, company, month):
        start, end = month_bounds(month)
        with connect(self.db) as con:
            authorize(con, user, company)
            if month != "2026-09":
                raise BusinessError("out_of_scope", "初赛仅检查2026年9月的用途完整性，其他月份可查询金额。")
            rule = select_rule(con, company, start, ("purpose_all", "purpose_threshold"))
            invoices = con.execute("SELECT * FROM invoices WHERE company_id=? AND invoice_date>=? AND invoice_date<? ORDER BY invoice_id", (company, start, end)).fetchall()
            missing = [public_invoice(r) for r in invoices if not r["purpose"].strip() and (rule["kind"] == "purpose_all" or r["amount_cents"] >= rule["threshold_cents"])]
        return {"company_id": company, "month": month, "invoice_count": len(invoices), "missing_count": len(missing), "missing": missing, "rule": rule}

    def update(self, user, company, invoice_id, changes, operation_id=None, expected_before=None):
        if not isinstance(changes, dict) or not changes:
            raise BusinessError("invalid_changes", "至少提供一个要修改的用途或备注字段。")
        if set(changes) - {"purpose", "remark"}:
            raise BusinessError("field_forbidden", "只允许修改发票用途 purpose 和备注 remark。")
        if any(not isinstance(v, str) or len(v) > 2000 for v in changes.values()):
            raise BusinessError("invalid_changes", "用途和备注必须为不超过2000字符的文本。")
        operation_id = operation_id or str(uuid4())
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 200:
            raise BusinessError("invalid_operation", "操作编号必须为1至200字符的非空文本。")
        encoded = json.dumps(changes, ensure_ascii=False, sort_keys=True)
        with connect(self.db) as con:
            with con:
                con.execute("BEGIN IMMEDIATE")
                authorize(con, user, company, write=True)
                prior = con.execute("SELECT * FROM audit_log WHERE operation_id=?", (operation_id,)).fetchone()
                if prior:
                    if (prior["user_id"], prior["company_id"], prior["invoice_id"], prior["changes_json"]) != (user, company, invoice_id, encoded):
                        raise BusinessError("operation_conflict", "该操作编号已被其他修改使用，请使用新的操作编号。")
                    replayed, changed = True, False
                else:
                    before = con.execute("SELECT * FROM invoices WHERE company_id=? AND invoice_id=?", (company, invoice_id)).fetchone()
                    if before is None:
                        raise BusinessError("not_found", "该企业下没有找到指定发票。")
                    if expected_before is not None and public_invoice(before) != expected_before:
                        raise BusinessError("stale_draft", "发票已被其他操作更改，请重新提出修改。")
                    changed = any(before[k] != v for k, v in changes.items())
                    # 字段名已经过白名单校验；字段值始终参数化。
                    fields = ",".join(f"{key}=?" for key in changes)
                    con.execute(f"UPDATE invoices SET {fields} WHERE company_id=? AND invoice_id=?", (*changes.values(), company, invoice_id))
                    after = con.execute("SELECT * FROM invoices WHERE company_id=? AND invoice_id=?", (company, invoice_id)).fetchone()
                    con.execute("INSERT INTO audit_log VALUES(?,?,?,?,?,?,?,?)", (operation_id, user, company, invoice_id, encoded, json.dumps(public_invoice(before), ensure_ascii=False), json.dumps(public_invoice(after), ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
                    replayed = False
        # 提交成功后通过新连接回读，不能仅凭 UPDATE 执行成功宣称已保存。
        readback = self.invoice(user, company, invoice_id)
        matches = all(readback[k] == v for k, v in changes.items())
        return {"operation_id": operation_id, "saved": True, "changed": changed, "replayed": replayed, "matches_requested": matches, "readback": readback}

    def audit(self, user, company):
        with connect(self.db) as con:
            authorize(con, user, company)
            rows = con.execute("SELECT * FROM audit_log WHERE company_id=? ORDER BY created_at DESC LIMIT 100", (company,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for key in ("changes_json", "before_json", "after_json"):
                item[key.removesuffix("_json")] = json.loads(item.pop(key))
            result.append(item)
        return {"company_id": company, "operations": result}
