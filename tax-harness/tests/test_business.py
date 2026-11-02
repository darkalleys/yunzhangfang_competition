import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tax_harness.__main__ import main
from tax_harness.excel import cents
from tax_harness.service import Service
from tax_harness.store import BusinessError, ROOT, initialize


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="test-", dir=ROOT / "data")
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "test.sqlite3"
        initialize(self.db)
        self.service = Service(self.db)

    def assert_error(self, code, fn, *args, **kwargs):
        with self.assertRaises(BusinessError) as error:
            fn(*args, **kwargs)
        self.assertEqual(code, error.exception.code)

    def raw(self, sql, params=()):
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            return con.execute(sql, params).fetchall()

    def test_import_counts_and_types(self):
        for table, expected in (("companies", 2), ("users", 2), ("invoices", 40), ("bank_records", 48), ("rules", 5)):
            self.assertEqual(expected, self.raw(f"SELECT COUNT(*) FROM {table}")[0][0])
        self.assertEqual([("integer",)], self.raw("SELECT DISTINCT typeof(amount_cents) FROM invoices"))
        self.assertEqual([("", "")], self.raw("SELECT purpose,remark FROM invoices WHERE company_id='C001' AND invoice_id='F002'"))

    def test_all_four_totals_from_current_records(self):
        baselines = [
            ("C001", "2026-08", "9046.35", "5720.99", "14850.75"),
            ("C001", "2026-09", "9622.06", "7180.74", "13000.50"),
            ("C002", "2026-08", "13667.05", "9341.10", "18800.25"),
            ("C002", "2026-09", "12667.24", "8087.24", "13700.75"),
        ]
        for company, month, invoice, expense, income in baselines:
            with self.subTest(company=company, month=month):
                result = self.service.totals("U001", company, month)
                self.assertEqual((invoice, expense, income), (result["invoice_total"], result["bank_expense"], result["bank_income"]))
                self.assertEqual((10, 12), (result["invoice_count"], result["bank_count"]))

    def test_september_missing_and_versions(self):
        for company, expected, rule_id, version in (
            ("C001", ["F002", "F003", "F004", "F006", "F009"], "R002", "2.0"),
            ("C002", ["F002", "F005", "F006"], "R003", "1.0"),
        ):
            with self.subTest(company=company):
                result = self.service.check("U001", company, "2026-09")
                self.assertEqual(expected, [r["invoice_id"] for r in result["missing"]])
                self.assertEqual((rule_id, version, "active"), (result["rule"]["rule_id"], result["rule"]["version"], result["rule"]["status"]))

    def test_permission_for_every_read_tool_and_write(self):
        self.assertEqual("9622.06", self.service.totals("U002", "C001", "2026-09")["invoice_total"])
        self.assertEqual(5, self.service.check("U002", "C001", "2026-09")["missing_count"])
        self.assertEqual("F002", self.service.invoice("U002", "C001", "F002")["invoice_id"])
        for user, company in (("U002", "C002"), ("U999", "C001"), ("U001", "C999")):
            for method, tail in ((self.service.totals, ("2026-09",)), (self.service.check, ("2026-09",)), (self.service.invoice, ("F002",)), (self.service.audit, ())):
                with self.subTest(user=user, company=company, method=method.__name__):
                    self.assert_error("permission_denied", method, user, company, *tail)
        for company in ("C001", "C002"):
            self.assert_error("permission_denied", self.service.update, "U002", company, "F002", {"purpose": "不得保存"})
        self.assertEqual("", self.service.invoice("U001", "C001", "F002")["purpose"])
        self.assertEqual(0, len(self.service.audit("U001", "C001")["operations"]))

    def test_update_persistence_readback_and_same_id_isolation(self):
        other = self.service.invoice("U001", "C002", "F002")
        original = self.service.invoice("U001", "C001", "F002")
        result = self.service.update("U001", "C001", "F002", {"purpose": "客户资料打印", "remark": "用户明确补充"})
        self.assertTrue(result["saved"] and result["matches_requested"])
        current = Service(self.db).invoice("U001", "C001", "F002")
        self.assertEqual("客户资料打印", current["purpose"])
        self.assertEqual(current, result["readback"])
        self.assertEqual(other, self.service.invoice("U001", "C002", "F002"))
        for key in ("amount", "invoice_date", "seller", "item", "company_id", "invoice_id"):
            self.assertEqual(original[key], current[key])
        self.assertEqual(4, self.service.check("U001", "C001", "2026-09")["missing_count"])
        self.assertEqual(3, self.service.check("U001", "C002", "2026-09")["missing_count"])
        log = self.service.audit("U001", "C001")["operations"][0]
        self.assertEqual("", log["before"]["purpose"])
        self.assertEqual("客户资料打印", log["after"]["purpose"])

    def test_read_only_fields_rejected_atomically(self):
        original = self.service.invoice("U001", "C001", "F002")
        bank = self.raw("SELECT * FROM bank_records")
        for key in ("amount", "amount_cents", "invoice_date", "company_id", "seller", "item", "invoice_id", "direction"):
            self.assert_error("field_forbidden", self.service.update, "U001", "C001", "F002", {"purpose": "不能部分保存", key: "999"})
        self.assertEqual(original, self.service.invoice("U001", "C001", "F002"))
        self.assertEqual(bank, self.raw("SELECT * FROM bank_records"))

    def test_remark_does_not_replace_purpose_and_whitespace_is_empty(self):
        self.service.update("U001", "C001", "F002", {"remark": "已提供说明", "purpose": " \t\u3000"})
        self.assertEqual(5, self.service.check("U001", "C001", "2026-09")["missing_count"])

    def test_optional_below_threshold_can_be_filled(self):
        self.service.update("U001", "C002", "F004", {"purpose": "用户自愿补充"})
        self.assertEqual(3, self.service.check("U001", "C002", "2026-09")["missing_count"])

    def test_correction_and_clearing_are_current(self):
        for value in ("第一版", "更正用途", ""):
            self.service.update("U001", "C001", "F002", {"purpose": value})
            self.assertEqual(value, self.service.invoice("U001", "C001", "F002")["purpose"])
        self.assertEqual(5, self.service.check("U001", "C001", "2026-09")["missing_count"])

    def test_no_records_distinct_from_permission_or_failure(self):
        for company in ("C001", "C002"):
            result = self.service.totals("U001", company, "2026-07")
            self.assertTrue(result["no_records"])
            self.assertEqual(("0.00", "0.00", "0.00"), (result["invoice_total"], result["bank_income"], result["bank_expense"]))
        self.assert_error("permission_denied", self.service.totals, "U002", "C002", "2026-07")
        self.assert_error("not_initialized", Service(Path(self.tmp.name) / "missing.db").totals, "U001", "C001", "2026-09")

    def test_invalid_month_and_scope(self):
        for month in (None, "", "2026-9", "2026-13", "2026-00", "本月"):
            self.assert_error("invalid_month", self.service.totals, "U001", "C001", month)
        self.assert_error("out_of_scope", self.service.check, "U001", "C001", "2026-08")

    def test_init_does_not_overwrite_saved_data(self):
        self.service.update("U001", "C001", "F002", {"purpose": "持久化验证"})
        self.assertFalse(initialize(self.db)["created"])
        self.assertEqual("持久化验证", self.service.invoice("U001", "C001", "F002")["purpose"])

    def test_idempotency_and_conflict(self):
        args = ("U001", "C001", "F002", {"purpose": "重复调用"})
        self.service.update(*args, operation_id="op-1")
        result = self.service.update(*args, operation_id="op-1")
        self.assertTrue(result["replayed"])
        self.assertEqual(1, len(self.service.audit("U001", "C001")["operations"]))
        self.assert_error("operation_conflict", self.service.update, "U001", "C001", "F002", {"purpose": "不同修改"}, operation_id="op-1")

    def test_not_found_invalid_changes_and_failed_write(self):
        self.assert_error("not_found", self.service.invoice, "U001", "C001", "F999")
        self.assert_error("not_found", self.service.update, "U001", "C001", "F999", {"purpose": "不存在"})
        for changes in ({}, {"purpose": None}, {"purpose": "字" * 2001}):
            self.assert_error("invalid_changes", self.service.update, "U001", "C001", "F002", changes)
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            con.execute("CREATE TRIGGER simulate_failure BEFORE UPDATE ON invoices BEGIN SELECT RAISE(ABORT,'模拟保存失败'); END")
            con.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.update("U001", "C001", "F002", {"purpose": "不应保存"})
        self.assertEqual("", self.service.invoice("U001", "C001", "F002")["purpose"])
        self.assertEqual(0, len(self.service.audit("U001", "C001")["operations"]))

    def test_rule_is_read_from_database_not_hardcoded(self):
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            con.execute("UPDATE rules SET status='inactive' WHERE rule_id='R002' AND version='2.0'")
            con.commit()
        self.assert_error("rule_missing", self.service.check, "U001", "C001", "2026-09")

    def test_decimal_conversion(self):
        self.assertEqual(99999, cents("999.99"))
        self.assertEqual(100000, cents("1000.00"))
        self.assertEqual(100001, cents("1000.01"))
        for invalid in ("NaN", "Infinity", "-1", "1.001", "不是金额"):
            with self.assertRaises(ValueError):
                cents(invalid)

    def test_cli_json_success_and_error_exit(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exit_code = main(["--db", str(self.db), "--json", "totals", "--user", "U001", "--company", "C001", "--month", "2026-09"])
        self.assertEqual(0, exit_code)
        self.assertEqual("9622.06", json.loads(out.getvalue())["data"]["invoice_total"])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exit_code = main(["--db", str(self.db), "--json", "update", "--user", "U002", "--company", "C001", "--invoice", "F002", "--purpose", "不允许"])
        self.assertEqual(1, exit_code)
        self.assertEqual("", out.getvalue())
        self.assertEqual("permission_denied", json.loads(err.getvalue())["error"]["code"])


if __name__ == "__main__":
    unittest.main()
