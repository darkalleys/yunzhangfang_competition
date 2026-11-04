"""真实模型长对话及离线恢复验收；只使用隔离临时库。"""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from urllib.error import URLError
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tax_harness.chat import ChatSession
from tax_harness.service import Service
from tax_harness.store import initialize,BusinessError


def main():
    out=ROOT/'reports'/'phase4'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]);out.mkdir(parents=True)
    report={'model':'qwen3:8b','checks':[]}
    with tempfile.TemporaryDirectory(prefix='test-phase4-long-',dir=ROOT/'data') as temp:
        db=Path(temp)/'test.sqlite3';initialize(db)
        session=ChatSession('U001','C001',db,trace_dir=out/'traces')
        session.turn('检查2026年9月缺少用途的发票。')
        for i in range(12):session.turn(f'这是第{i+1}轮补充交流，请只回复收到，暂时不用查询或修改任何资料。')
        report['checks'].append({'name':'bounded_real_history','passed':len(session.turns)<=8,'retained_turns':len(session.turns)})
        Service(db).update('U001','C001','F002',{'purpose':'另一会话明确保存'})
        reply=session.turn('现在继续上次的检查，重新查询还有哪些发票必须补用途？')
        expected=['F003','F004','F006','F009']
        report['checks'].append({'name':'long_dialogue_fresh_data','passed':all(x in reply for x in expected) and session.memory.snapshot()['task']['missing_ids']==expected,'answer':reply})
        session.turn('将F003的用途填写为业务资料邮寄。')
        draft_exists=session.pending is not None
        error=None
        with patch('tax_harness.chat.urlopen',side_effect=URLError('验收中模拟本地模型离线')):
            try:session.turn('暂时不改，先查询九月金额。')
            except BusinessError as exc:error=exc.code
        report['checks'].append({'name':'offline_clears_draft_no_write','passed':draft_exists and error=='model_unavailable' and session.pending is None and Service(db).invoice('U001','C001','F003')['purpose']==''})
        reply=session.turn('模型恢复后，请重新查询2026年9月的发票总额。')
        report['checks'].append({'name':'model_recovery','passed':'9622.06' in reply,'answer':reply})
        restored=ChatSession('U001','C001',db,trace_dir=out/'traces')
        report['checks'].append({'name':'task_survives_failure','passed':restored.pending is None and restored.memory.snapshot()['task']['missing_ids']==expected})
    report['passed']=all(c['passed'] for c in report['checks'])
    (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));print('Evidence:',out)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
