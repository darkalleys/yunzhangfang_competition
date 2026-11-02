"""从Git阶段标签导出代码，再用真实数据库快照验证恢复副本。"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tax_harness.maintenance import backup, digest, restore
from tax_harness.service import Service
from tax_harness.store import DEFAULT_DB


def main():
    before = digest(DEFAULT_DB)
    report = {"time_utc": datetime.now(timezone.utc).isoformat(), "code_tag": "phase2-v0.2.0", "checks": []}
    with tempfile.TemporaryDirectory(prefix="test-recovery-", dir=ROOT / "data") as temporary:
        directory = Path(temporary).resolve()
        archive = directory / "code.zip"
        subprocess.run(["git", "archive", "--format=zip", f"--output={archive}", "phase2-v0.2.0"], cwd=ROOT.parent, check=True, capture_output=True)
        with ZipFile(archive) as package:
            for member in package.namelist():
                (directory / "code" / member).resolve().relative_to(directory / "code")
            package.extractall(directory / "code")
        old_root = directory / "code" / "tax-harness"
        tests = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=old_root, capture_output=True, text=True, encoding="utf-8", timeout=60)
        if tests.returncode:
            raise RuntimeError(tests.stdout + tests.stderr)
        report["checks"].append({"name": "archived_code_tests", "passed": True, "output": tests.stdout + tests.stderr})
        snapshot = backup(DEFAULT_DB, directory / "snapshots")
        restored = restore(snapshot, old_root / "data" / "recovered.sqlite3")
        command = [sys.executable, "-X", "utf8", "-m", "tax_harness", "--db", str(restored), "--json"]
        for name, tail, expected in (
            ("restored_invoice", ["invoice", "--user", "U001", "--company", "C001", "--invoice", "F002"], Service(DEFAULT_DB).invoice("U001", "C001", "F002")),
            ("restored_totals", ["totals", "--user", "U001", "--company", "C001", "--month", "2026-09"], Service(DEFAULT_DB).totals("U001", "C001", "2026-09")),
        ):
            result = subprocess.run(command + tail, cwd=old_root, capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
            actual = json.loads(result.stdout)["data"]
            assert actual == expected, name
            report["checks"].append({"name": name, "passed": True})
        original = Service(DEFAULT_DB).audit("U001", "C001")
        assert Service(restored).audit("U001", "C001") == original
        report["checks"].append({"name": "audit_preserved", "passed": True})
    assert before == digest(DEFAULT_DB), "当前业务库文件发生了变化"
    report["checks"].append({"name": "current_database_untouched", "passed": True})
    report["passed"] = True
    output = ROOT / "reports" / "recovery" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    output.mkdir(parents=True)
    report["evidence_path"] = str(output / "result.json")
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (output / "result.json").write_text(text, encoding="utf-8")
    (ROOT / "reports" / "recovery-verification.json").write_text(text, encoding="utf-8")
    print(f"恢复演练通过：{len(report['checks'])}项检查。记录：{output / 'result.json'}")


if __name__ == "__main__":
    main()
