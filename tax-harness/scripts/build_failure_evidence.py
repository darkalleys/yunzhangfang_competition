"""从已有真实失败报告和JSONL提取证据，不调用模型、不修改原报告。"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORTS=['stage2-live-qwen3-0.6b.json','stage2-live-qwen3-8b-initial.json']


def relative(path):return path.resolve().relative_to(ROOT).as_posix()


def locate(old):
    text=str(old).replace('\\','/')
    mark='/tax-harness/'
    if mark in text:text=text.split(mark,1)[1]
    candidate=ROOT/text
    return candidate if candidate.is_file() else None


def main():
    evidence=[]
    for name in REPORTS:
        report_path=ROOT/'reports'/name
        report=json.loads(report_path.read_text(encoding='utf-8'))
        trace_candidates=[]
        for check in report['checks']:
            p=locate(check.get('trace',''))
            if p and p not in trace_candidates:trace_candidates.append(p)
        for index,check in enumerate(report['checks']):
            if check['passed']:continue
            path=locate(check.get('trace',''))
            candidates=[path] if path else trace_candidates
            segment=[];source=None;first=None;last=None
            for candidate in candidates:
                rows=[json.loads(line) for line in candidate.read_text(encoding='utf-8').splitlines()]
                start=next((i for i,row in enumerate(rows) if row.get('event')=='user_input' and row.get('text')==check['question']),None)
                if start is None:continue
                end=next((i for i in range(start+1,len(rows)) if rows[i].get('event')=='user_input'),len(rows))
                segment=rows[start:end];source=candidate;first=start+1;last=end;break
            if not segment:raise ValueError('找不到原始失败轮次：'+check['name'])
            item={'id':f'F{len(evidence)+1:02d}','model':report['model'],'kind':'historical_real_model_failure',
                  'report':relative(report_path),'report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
                  'check_index':index,'check_name':check['name'],'question':check['question'],
                  'answer':check.get('answer'),'error':check.get('error'),'trace':relative(source),
                  'trace_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'trace_lines':[first,last],
                  'time_utc':segment[0].get('time_utc'),'session_id':segment[0].get('session_id'),
                  'model_request_count':sum(x.get('event')=='model_input' for x in segment),
                  'save_event_count':sum(x.get('event')=='confirmed_save' for x in segment),
                  'tools':[{'name':x.get('name'),'arguments':x.get('arguments'),'result':x.get('result')} for x in segment if x.get('event')=='tool_result'],
                  'model_outputs':[x.get('message') for x in segment if x.get('event')=='model_output']}
            evidence.append(item)
    assert len(evidence)==13
    target=ROOT/'reports'/'analysis'/'failure-evidence.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({'runtime_baseline':'bab7940 / 0.4.0','scope':'historical observed failures; not 13 independent root causes','cases':evidence},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Verified historical cases:',len(evidence));print(target)


if __name__=='__main__':main()
