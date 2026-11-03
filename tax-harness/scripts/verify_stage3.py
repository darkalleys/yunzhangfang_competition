"""真实模型跨会话验收，全部使用临时业务库。"""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tax_harness.store import initialize
from tax_harness.chat import ChatSession,Ollama
from tax_harness.service import Service


def main():
    out=ROOT/'reports'/'phase3'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]);out.mkdir(parents=True)
    result={'model':'qwen3:8b','checks':[]}
    with tempfile.TemporaryDirectory(prefix='test-phase3-live-',dir=ROOT/'data') as temp:
        db=Path(temp)/'business.sqlite3';initialize(db)
        model=Ollama()
        def new(user='U001',company='C001'):return ChatSession(user,company,db,model,trace_dir=out/'traces')
        first=new();first.turn('检查2026年9月缺少用途的发票。')
        first.turn('/pref style 回答保持简洁')
        first.turn('把F002用途填为客户培训资料打印。')
        second=new()
        checks=result['checks']
        checks.append({'name':'no_authorization_restored','passed':second.pending is None and '没有待确认' in second.turn('/confirm')})
        reply=second.turn('继续上次检查，列出还需要补用途的发票。')
        checks.append({'name':'model_resume','answer':reply,'passed':all(x in reply for x in ['F002','F003','F004','F006','F009']) and second.month=='2026-09'})
        second.turn('将F002用途填写为员工培训资料打印。');second.turn('/confirm')
        third=new();reply=third.turn('继续检查还有哪些缺项？')
        checks.append({'name':'fresh_progress','answer':reply,'passed':len(third.memory.snapshot()['task']['missing_ids'])==4 and all(x in reply for x in ['F003','F004','F006','F009'])})
        checks.append({'name':'preference_loaded','passed':third.memory.snapshot()['preferences'][0]['value']=='回答保持简洁'})
        third.turn('/pref style 回答详细');checks.append({'name':'preference_corrected','passed':new().memory.snapshot()['preferences'][0]['value']=='回答详细'})
        third.turn('/forget style');checks.append({'name':'preference_deleted','passed':new().memory.snapshot()['preferences']==[]})
        checks.append({'name':'user_company_isolation','passed':new('U002').memory.snapshot()=={'task':None,'preferences':[]} and new(company='C002').memory.snapshot()=={'task':None,'preferences':[]}})
        reply=third.turn('查询2026年9月适用的发票用途规则和版本。')
        checks.append({'name':'rule_lookup','answer':reply,'passed':'2.0' in reply and '甲企业' in reply})
    result['passed']=all(x['passed'] for x in checks)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));print('Evidence:',out)
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
