"""SQLite一致性备份及恢复到新文件，不覆盖当前业务库。"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from uuid import uuid4

from . import __version__
from .store import ROOT, SCHEMA, BASE_SCHEMA


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(con):
    rows = con.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def validate(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as con:
        if con.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("数据库完整性检查失败")
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("数据库外键检查失败")
        if con.execute("SELECT value FROM metadata WHERE key='material_version'").fetchone() != ("1.1.0",):
            raise ValueError("不支持的材料版本")
        actual = fingerprint(con)
    supported = []
    for schema in (SCHEMA, BASE_SCHEMA):
        with closing(sqlite3.connect(":memory:")) as expected:
            expected.executescript(schema)
            supported.append(fingerprint(expected))
    if actual not in supported:
        raise ValueError("数据库结构与当前代码不兼容，需先设计迁移，不能直接恢复使用")
    return actual


def code_revision():
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "tax-harness"], cwd=ROOT.parent, capture_output=True, text=True, timeout=5)
        return {"commit": result.stdout.strip() if result.returncode == 0 else None,
            "working_tree_dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None}
    except (OSError, subprocess.TimeoutExpired):
        return {"commit": None, "working_tree_dirty": None}


def backup(db, directory=None):
    db = Path(db).resolve()
    if not db.is_file():
        raise ValueError("源数据库不存在")
    parent = Path(directory) if directory else ROOT / "backups"
    snapshot = parent / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    snapshot.mkdir(parents=True, exist_ok=False)
    target = snapshot / "database.sqlite3"
    try:
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(target)) as destination:
                source.backup(destination)
        schema = validate(target)
        manifest = {"format": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "application_version": __version__, "code": code_revision(), "source_database": str(db),
            "sha256": digest(target), "schema_sha256": schema, "material_version": "1.1.0"}
        (snapshot / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return snapshot.resolve()
    except Exception:
        # 只清理本次新建的两个文件，不递归删除任意用户路径。
        target.unlink(missing_ok=True)
        (snapshot / "manifest.json").unlink(missing_ok=True)
        snapshot.rmdir()
        raise


def restore(snapshot, target):
    snapshot, target = Path(snapshot).resolve(), Path(target).resolve()
    source = snapshot / "database.sqlite3"
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or manifest.get("sha256") != digest(source):
        raise ValueError("备份格式或SHA256校验失败")
    if validate(source) != manifest.get("schema_sha256"):
        raise ValueError("备份结构校验失败")
    target.parent.mkdir(parents=True, exist_ok=True)
    # 独占创建，恢复始终到新文件，不存在覆盖开关。
    with target.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(target)) as dest:
                src.backup(dest)
        validate(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target
