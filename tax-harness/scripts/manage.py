"""本地管理员规则入口及用户记忆入口，不暴露给模型执行。"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tax_harness.store import DEFAULT_DB,BusinessError
from tax_harness.state import Memory,upgrade
from tax_harness.service import Service
from tax_harness import knowledge


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,default=DEFAULT_DB)
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('migrate')
    m=sub.add_parser('memory')
    m.add_argument('--user',required=True);m.add_argument('--company',required=True)
    m.add_argument('action',choices=['show','set','delete','task-clear','task-set'])
    m.add_argument('--key');m.add_argument('--value');m.add_argument('--month')
    r=sub.add_parser('rules');r.add_argument('action',choices=['list','import','status'])
    r.add_argument('--query',default='');r.add_argument('--file',type=Path)
    r.add_argument('--rule');r.add_argument('--version');r.add_argument('--status',choices=['active','inactive'])
    a=p.parse_args()
    try:
        if a.cmd=='migrate': result=upgrade(a.db)
        elif a.cmd=='memory':
            mem=Memory(a.db,a.user,a.company)
            if a.action=='show': result=mem.refresh()
            elif a.action=='set':
                if a.value is None: raise BusinessError('invalid_preference','set需要--value。')
                result=mem.preference(a.key,a.value)
            elif a.action=='delete': result=mem.preference(a.key)
            elif a.action=='task-clear': result=mem.clear_task()
            else:
                mem.track(Service(a.db).check(a.user,a.company,a.month)); result=mem.snapshot()
        elif a.action=='list': result=knowledge.list_rules(a.db,a.query)
        elif a.action=='import':
            if not a.file: raise BusinessError('invalid_rule','需要--file JSON文件。')
            result=knowledge.import_rules(a.db,json.loads(a.file.read_text(encoding='utf-8-sig')))
        else: result=knowledge.status(a.db,a.rule,a.version,a.status)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    except (BusinessError,ValueError,OSError,sqlite3.Error) as exc:
        print(f'操作失败：{exc}',file=sys.stderr);return 1


if __name__=='__main__': raise SystemExit(main())
