"""按用户、企业隔离的任务与明确偏好；从不持久化保存授权。"""
from datetime import datetime, timezone
import json

from .service import Service, authorize
from .store import BusinessError, STATE_SCHEMA, connect


def now():
    return datetime.now(timezone.utc).isoformat()


def upgrade(db, backup_directory=None):
    from .maintenance import backup, validate
    validate(db)
    with connect(db) as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "tasks" in tables:
        return {"migrated": False, "message": "已经是第三阶段结构，未重复迁移。"}
    snapshot = backup(db,backup_directory)
    with connect(db) as con:
        try:
            con.executescript("BEGIN IMMEDIATE;" + STATE_SCHEMA + "COMMIT;")
        except Exception:
            con.rollback()
            raise
    validate(db)
    return {"migrated": True, "backup": str(snapshot), "message": "已备份并完成增量迁移，原业务表与规则未重置。"}


class Memory:
    def __init__(self, db, user, company):
        self.db, self.user, self.company = db, user, company
        with connect(db) as con:
            authorize(con, user, company)
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='tasks'").fetchone():
                raise BusinessError("migration_required", "请先运行 python -m tax_harness migrate，升级前会自动备份。")

    def event(self, con, action, key):
        con.execute("INSERT INTO state_events(user_id,company_id,action,object_key,created_at) VALUES(?,?,?,?,?)", (self.user,self.company,action,key,now()))

    def snapshot(self):
        with connect(self.db) as con:
            authorize(con, self.user, self.company)
            task = con.execute("SELECT month,missing_json,updated_at FROM tasks WHERE user_id=? AND company_id=?", (self.user,self.company)).fetchone()
            prefs = con.execute("SELECT key,value,source,updated_at FROM preferences WHERE user_id=? AND company_id=? ORDER BY key", (self.user,self.company)).fetchall()
        return {"task": {"month": task["month"], "missing_ids": json.loads(task["missing_json"]), "updated_at": task["updated_at"]} if task else None,
                "preferences": [dict(p) for p in prefs]}

    def track(self, result):
        with connect(self.db) as con, con:
            authorize(con, self.user, self.company)
            ids = [r["invoice_id"] for r in result["missing"]]
            if ids:
                con.execute("INSERT INTO tasks VALUES(?,?,?,?,?) ON CONFLICT(user_id,company_id) DO UPDATE SET month=excluded.month,missing_json=excluded.missing_json,updated_at=excluded.updated_at", (self.user,self.company,result["month"],json.dumps(ids),now()))
            else:
                con.execute("DELETE FROM tasks WHERE user_id=? AND company_id=?", (self.user,self.company))
            self.event(con,"task_refreshed",result["month"])

    def refresh(self):
        task = self.snapshot()["task"]
        if task:
            # 规则缺失或查询失败时保留任务，不能误报已完成。
            self.track(Service(self.db).check(self.user,self.company,task["month"]))
        return self.snapshot()

    def preference(self, key, value=None):
        if not isinstance(key,str) or not key.strip() or len(key)>80:
            raise BusinessError("invalid_preference", "偏好名称须为1至80字符。")
        if value is not None and (not isinstance(value,str) or not value.strip() or len(value)>500):
            raise BusinessError("invalid_preference", "偏好内容须为1至500字符。")
        with connect(self.db) as con, con:
            authorize(con,self.user,self.company)
            if value is None:
                con.execute("DELETE FROM preferences WHERE user_id=? AND company_id=? AND key=?",(self.user,self.company,key))
                self.event(con,"preference_deleted",key)
            else:
                count=con.execute('SELECT COUNT(*) FROM preferences WHERE user_id=? AND company_id=?',(self.user,self.company)).fetchone()[0]
                exists=con.execute('SELECT 1 FROM preferences WHERE user_id=? AND company_id=? AND key=?',(self.user,self.company,key)).fetchone()
                if count>=10 and not exists:
                    raise BusinessError('preference_limit','每个用户、企业最多10项偏好，请先删除不需要的偏好。')
                con.execute("INSERT INTO preferences VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,company_id,key) DO UPDATE SET value=excluded.value,source=excluded.source,updated_at=excluded.updated_at",(self.user,self.company,key,value,"用户明确通过偏好管理入口设置",now()))
                self.event(con,"preference_set",key)
        return self.snapshot()

    def clear_task(self):
        with connect(self.db) as con, con:
            authorize(con,self.user,self.company)
            con.execute("DELETE FROM tasks WHERE user_id=? AND company_id=?",(self.user,self.company))
            self.event(con,"task_deleted","active")
        return self.snapshot()
