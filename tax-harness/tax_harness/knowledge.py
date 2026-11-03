"""本地规则管理：版本不可静默覆盖，正文与结构化执行条件一起维护。"""
from datetime import date
import json
from .store import BusinessError, connect
from .state import now

FIELDS = {'rule_id','version','name','company_id','effective_date','status','kind','threshold_cents','text'}
KINDS = {'amounts','bank','purpose_all','purpose_threshold'}


def checked(rule):
    if not isinstance(rule,dict) or set(rule) != FIELDS:
        raise BusinessError("invalid_rule", "规则字段必须与data/rules.json示例一致。")
    for key in ('rule_id','version','name','text'):
        if not isinstance(rule[key],str) or not rule[key].strip() or len(rule[key])>4000:
            raise BusinessError("invalid_rule", "规则编号、版本、名称、正文必须是有效文本。")
    if rule['company_id'] not in (None,'C001','C002') or rule['status'] not in ('active','inactive') or rule['kind'] not in KINDS:
        raise BusinessError("invalid_rule", "企业、状态或执行类型无效。")
    try:
        if date.fromisoformat(rule['effective_date']).isoformat()!=rule['effective_date']:
            raise ValueError('date must be canonical')
    except (TypeError,ValueError):
        raise BusinessError("invalid_rule", "生效日期必须为YYYY-MM-DD。")
    threshold = rule['threshold_cents']
    if rule['kind']=='purpose_threshold':
        if type(threshold) is not int or threshold<0:
            raise BusinessError("invalid_rule", "门槛必须是非负整数分。")
    elif threshold is not None:
        raise BusinessError("invalid_rule", "非门槛类型的threshold_cents必须为空。")
    return rule


def conflicts(con):
    rows = con.execute("SELECT * FROM rules WHERE status='active'").fetchall()
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            group = lambda r: 'purpose' if r['kind'].startswith('purpose_') else r['kind']
            if group(a)==group(b) and a['effective_date']==b['effective_date'] and (a['company_id']==b['company_id'] or a['company_id'] is None or b['company_id'] is None):
                raise BusinessError("rule_conflict", "同企业、同日存在冲突的启用规则，请先停用旧版或调整生效日期。")


def list_rules(db, query=''):
    with connect(db) as con:
        return [dict(r) for r in con.execute("SELECT * FROM rules WHERE instr(name,?)>0 OR instr(text,?)>0 OR instr(rule_id,?)>0 ORDER BY rule_id,effective_date,version",(query,query,query))]


def import_rules(db, rules):
    if not isinstance(rules,list) or not rules or len(rules)>100:
        raise BusinessError("invalid_rule", "每次导入1至100条规则的JSON数组。")
    rules = [checked(r) for r in rules]
    with connect(db) as con, con:
        for r in rules:
            old = con.execute("SELECT * FROM rules WHERE rule_id=? AND version=?",(r['rule_id'],r['version'])).fetchone()
            if old:
                if dict(old)!=r:
                    raise BusinessError("version_immutable", "同编号版本不得覆盖，请导入新版本；状态请使用status命令维护。")
                continue
            con.execute("INSERT INTO rules VALUES(?,?,?,?,?,?,?,?,?)",tuple(r[k] for k in ('rule_id','version','name','company_id','effective_date','status','kind','threshold_cents','text')))
            con.execute("INSERT INTO rule_events(rule_id,version,action,created_at) VALUES(?,?,?,?)",(r['rule_id'],r['version'],'import',now()))
        conflicts(con)
    return {'imported_or_existing':len(rules)}


def status(db, rule_id, version, value):
    if value not in ('active','inactive'):
        raise BusinessError("invalid_rule", "状态须为active或inactive。")
    with connect(db) as con, con:
        row = con.execute("SELECT * FROM rules WHERE rule_id=? AND version=?",(rule_id,version)).fetchone()
        if not row:
            raise BusinessError("not_found", "规则版本不存在。")
        con.execute("UPDATE rules SET status=? WHERE rule_id=? AND version=?",(value,rule_id,version))
        conflicts(con)
        con.execute("INSERT INTO rule_events(rule_id,version,action,created_at) VALUES(?,?,?,?)",(rule_id,version,value,now()))
    return {'rule_id':rule_id,'version':version,'status':value}
