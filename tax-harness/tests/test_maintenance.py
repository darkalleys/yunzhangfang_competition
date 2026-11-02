from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tax_harness.maintenance import backup, restore
from tax_harness.service import Service
from tax_harness.store import ROOT, initialize


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="test-backup-", dir=ROOT / "data")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.db = self.directory / "source.sqlite3"
        initialize(self.db)

    def test_restore_preserves_snapshot_and_audit(self):
        service = Service(self.db)
        service.update("U001", "C001", "F002", {"purpose": "备份时用途"})
        snapshot = backup(self.db, self.directory / "backups")
        service.update("U001", "C001", "F002", {"purpose": "备份后更正"})
        restored = restore(snapshot, self.directory / "restored.sqlite3")
        self.assertEqual("备份时用途", Service(restored).invoice("U001", "C001", "F002")["purpose"])
        self.assertEqual("备份后更正", service.invoice("U001", "C001", "F002")["purpose"])
        self.assertEqual(1, len(Service(restored).audit("U001", "C001")["operations"]))
        self.assertEqual("", Service(restored).invoice("U001", "C002", "F002")["purpose"])

    def test_refuses_existing_target(self):
        snapshot = backup(self.db, self.directory / "backups")
        with self.assertRaises(FileExistsError):
            restore(snapshot, self.db)

    def test_corruption_is_rejected(self):
        snapshot = backup(self.db, self.directory / "backups")
        with (snapshot / "database.sqlite3").open("ab") as stream:
            stream.write(b"damaged")
        target = self.directory / "restored.sqlite3"
        with self.assertRaises(ValueError):
            restore(snapshot, target)
        self.assertFalse(target.exists())

    def test_schema_change_requires_migration(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("ALTER TABLE invoices ADD COLUMN new_schema_field TEXT")
            con.commit()
        with self.assertRaises(ValueError):
            backup(self.db, self.directory / "backups")

    def test_wal_uncheckpointed_data_is_backed_up(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("UPDATE invoices SET purpose='WAL中的已提交值' WHERE company_id='C001' AND invoice_id='F002'")
            con.commit()
            snapshot = backup(self.db, self.directory / "backups")
        restored = restore(snapshot, self.directory / "restored.sqlite3")
        self.assertEqual("WAL中的已提交值", Service(restored).invoice("U001", "C001", "F002")["purpose"])


if __name__ == "__main__":
    unittest.main()
