from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .excel import cents, iso_date, read_workbook

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "business.sqlite3"
DEFAULT_SOURCE = ROOT / "data" / "source" / "02_示例数据.xlsx"

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE companies (company_id TEXT PRIMARY KEY, name TEXT NOT NULL, alias TEXT NOT NULL);
CREATE TABLE users (user_id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE permissions (
 user_id TEXT REFERENCES users, company_id TEXT REFERENCES companies,
 can_read INTEGER NOT NULL CHECK(can_read IN (0,1)),
 can_write INTEGER NOT NULL CHECK(can_write IN (0,1) AND can_write <= can_read),
 PRIMARY KEY(user_id, company_id));
CREATE TABLE invoices (
 company_id TEXT REFERENCES companies, invoice_id TEXT, invoice_date TEXT NOT NULL,
 seller TEXT NOT NULL, item TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
 purpose TEXT NOT NULL DEFAULT '', remark TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(company_id, invoice_id));
CREATE TABLE bank_records (
 company_id TEXT REFERENCES companies, record_id TEXT, transaction_date TEXT NOT NULL,
 direction TEXT NOT NULL CHECK(direction IN ('收入','支出')),
 amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), counterparty TEXT NOT NULL,
 remark TEXT NOT NULL DEFAULT '', PRIMARY KEY(company_id, record_id));
CREATE TABLE rules (
 rule_id TEXT, version TEXT, name TEXT NOT NULL, company_id TEXT REFERENCES companies,
 effective_date TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','inactive')),
 kind TEXT NOT NULL, threshold_cents INTEGER, text TEXT NOT NULL,
 PRIMARY KEY(rule_id, version));
CREATE TABLE audit_log (
 operation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, company_id TEXT NOT NULL,
 invoice_id TEXT NOT NULL, changes_json TEXT NOT NULL, before_json TEXT NOT NULL,
 after_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX invoice_month ON invoices(company_id, invoice_date);
CREATE INDEX bank_month ON bank_records(company_id, transaction_date);
"""


class BusinessError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@contextmanager
def connect(db):
    path = Path(db)
    if not path.is_file():
        raise BusinessError("not_initialized", "数据库尚未初始化，请先运行 init。")
    # mode=rw 防止路径错误时静默创建一个空库。
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
    finally:
        con.close()


def initialize(db=DEFAULT_DB, source=DEFAULT_SOURCE):
    db, source = Path(db), Path(source)
    if db.exists():
        with connect(db) as con:
            marker = con.execute("SELECT value FROM metadata WHERE key='material_version'").fetchone()
            if not marker or marker[0] != "1.1.0":
                raise BusinessError("invalid_database", "已有数据库不属于当前材料版本。")
        return {"created": False, "database": str(db.resolve()), "message": "数据库已存在，保留当前保存的数据，不重复导入。"}
    if not source.is_file():
        raise BusinessError("source_missing", f"找不到示例数据：{source}")
    sheets = read_workbook(source)
    for name in ("企业与用户", "发票", "银行流水"):
        if name not in sheets:
            raise BusinessError("invalid_source", f"缺少工作表：{name}")
    companies = [r for r in sheets["企业与用户"] if r.get("A") in ("C001", "C002")]
    users = [r for r in sheets["企业与用户"] if r.get("A") in ("U001", "U002")]
    invoices = [r for r in sheets["发票"] if r.get("A") in ("C001", "C002")]
    bank = [r for r in sheets["银行流水"] if r.get("A") in ("C001", "C002")]
    if (len(companies), len(users), len(invoices), len(bank)) != (2, 2, 40, 48):
        raise BusinessError("invalid_source", "材料记录数不符，预期2家企业、2个用户、40张发票、48条流水。")
    rules = json.loads((ROOT / "data" / "rules.json").read_text(encoding="utf-8"))
    db.parent.mkdir(parents=True, exist_ok=True)
    # 独占创建，避免意外覆盖已有数据。
    with db.open("xb"):
        pass
    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript(SCHEMA)
        with con:
            con.executemany("INSERT INTO companies VALUES(?,?,?)", [(r["A"], r["B"], r["C"]) for r in companies])
            con.executemany("INSERT INTO users VALUES(?,?)", [(r["A"], r["B"]) for r in users])
            for user in users:
                for company, col in (("C001", "C"), ("C002", "D")):
                    permission = user.get(col)
                    if permission not in ("可查看并修改", "仅查看", "无权访问"):
                        raise BusinessError("invalid_source", "无法识别用户权限。")
                    con.execute("INSERT INTO permissions VALUES(?,?,?,?)", (user["A"], company, int(permission != "无权访问"), int(permission == "可查看并修改")))
            con.executemany("INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?)", [
                (r["A"], r["B"], iso_date(r["C"]), r["D"], r["E"], cents(r["F"]), r.get("G") or "", r.get("H") or "") for r in invoices])
            con.executemany("INSERT INTO bank_records VALUES(?,?,?,?,?,?,?)", [
                (r["A"], r["B"], iso_date(r["C"]), r["D"], cents(r["E"]), r["F"], r.get("G") or "") for r in bank])
            for rule in rules:
                con.execute("INSERT INTO rules VALUES(?,?,?,?,?,?,?,?,?)", (
                    rule["rule_id"], rule["version"], rule["name"], rule["company_id"], rule["effective_date"], rule["status"], rule["kind"], rule["threshold_cents"], rule["text"]))
            con.executemany("INSERT INTO metadata VALUES(?,?)", [
                ("material_version", "1.1.0"), ("source_sha256", hashlib.sha256(source.read_bytes()).hexdigest()),
                ("imported_at", datetime.now(timezone.utc).isoformat())])
    except Exception:
        con.close()
        db.unlink()  # 只删除本次独占创建且导入失败的文件。
        raise
    finally:
        con.close()
    return {"created": True, "database": str(db.resolve()), "companies": 2, "users": 2, "invoices": 40, "bank_records": 48, "rules": len(rules)}
