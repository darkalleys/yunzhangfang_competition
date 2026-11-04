"""真实Edge与Ollama网页验收，所有修改使用隔离测试库。"""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
import threading
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tax_harness.store import initialize
from tax_harness.web import Application,make_server
from tax_harness.service import Service
from browser_driver import Browser


def main():
    out=ROOT/'reports'/'phase4'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]);out.mkdir(parents=True)
    report={'checks':[],'model':'qwen3:8b','browser':'Microsoft Edge headless'}
    with tempfile.TemporaryDirectory(prefix='test-browser-',dir=ROOT/'data') as temp:
        folder=Path(temp);db=folder/'business.sqlite3';initialize(db)
        app=Application(db,trace_dir=out/'traces');server=make_server(app,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        browser=None
        try:
            browser=Browser(f'http://127.0.0.1:{server.server_port}',folder/'edge-profile')
            b=browser
            b.wait("document.readyState==='complete' && typeof api==='function'")
            def value(id,text): b.evaluate(f'document.getElementById({json.dumps(id)}).value={json.dumps(text)}')
            def click(id): b.evaluate(f'document.getElementById({json.dumps(id)}).click()')
            def done():b.wait('!busy',180)
            def submit(id):b.evaluate(f'document.getElementById({json.dumps(id)}).requestSubmit()');done()
            def send(text):value('prompt',text);submit('chat-form')
            def check(name,condition):
                assert condition,name
                report['checks'].append({'name':name,'passed':True})
            submit('connection')
            check('connected_totals',b.evaluate("document.getElementById('invoice-total').textContent==='9622.06'"))
            send('检查2026年9月缺少用途的发票。')
            check('natural_query_and_task',b.evaluate("document.getElementById('messages').textContent.includes('F009')") and app.sessions[next(iter(app.sessions))]['chat'].memory.snapshot()['task'] is not None)
            click('tab-memory');value('pref-key','style');value('pref-value','回答简洁');submit('pref-form')
            check('preference_button',b.evaluate("document.getElementById('preferences').textContent.includes('回答简洁')"))
            send('将F002用途填写为员工培训资料打印。')
            check('draft_not_saved',b.evaluate("!document.getElementById('draft').hidden") and Service(db).invoice('U001','C001','F002')['purpose']=='')
            b.screenshot(out/'desktop-draft.png')
            click('confirm');done()
            check('confirm_save_readback',Service(db).invoice('U001','C001','F002')['purpose']=='员工培训资料打印')
            check('other_company_unchanged',Service(db).invoice('U001','C002','F002')['purpose']=='')
            submit('connection')
            check('resume_task_no_draft',b.evaluate("document.getElementById('messages').textContent.includes('恢复') && document.getElementById('draft').hidden && document.getElementById('task').textContent.includes('4 张')"))
            click('tab-memory')
            b.evaluate("document.querySelector('#preferences button').click()");done()
            check('delete_preference_button',b.evaluate("document.getElementById('preferences').textContent.includes('尚未设置')"))
            click('tab-rules');check('rules_visible',b.evaluate("document.getElementById('rules').textContent.includes('2.0版') && document.getElementById('rules').textContent.includes('已停用')"))
            click('tab-records');click('load-trace');done()
            check('trace_current_session',b.evaluate("document.getElementById('trace').textContent.includes('memory_loaded')"))
            value('user','U002');b.evaluate("document.getElementById('user').dispatchEvent(new Event('change'))");done()
            check('scope_change_requires_new_session',b.evaluate("document.getElementById('prompt').disabled && document.getElementById('invoice-total').textContent==='—'"))
            submit('connection')
            send('将F003用途填写为业务资料邮寄。')
            check('readonly_denied',Service(db).invoice('U001','C001','F003')['purpose']=='' and b.evaluate("document.getElementById('draft').hidden && document.getElementById('messages').textContent.includes('权限')"))
            value('company','C002');submit('connection')
            check('unauthorized_scope_clears_data',b.evaluate("document.getElementById('status').textContent.includes('无权') && document.getElementById('invoice-total').textContent==='—'"))
            value('user','U001');value('company','C001');submit('connection');click('tab-data')
            b.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
            check('mobile_no_horizontal_overflow',b.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
            b.screenshot(out/'mobile.png')
            b.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
            b.screenshot(out/'desktop.png')
            check('no_browser_exceptions',not b.errors)
            report['passed']=True
        except Exception as exc:
            report['passed']=False;report['error']=str(exc)
            if browser:
                try:browser.screenshot(out/'failure.png')
                except Exception:pass
            raise
        finally:
            if browser:browser.close()
            server.shutdown();server.server_close()
            (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False,indent=2));print('Evidence:',out,flush=True)


if __name__=='__main__':main()
