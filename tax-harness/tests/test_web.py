import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from tax_harness.web import Application,make_server
from tax_harness.chat import ChatSession
from tax_harness.store import ROOT,initialize,BusinessError
from tax_harness.service import Service


class Answer:
    model='test-double'
    def chat(self,messages,tools): return {'role':'assistant','content':'请继续提供具体信息。'}


class WebTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='test-web-',dir=ROOT/'data');self.addCleanup(temp.cleanup)
        self.folder=Path(temp.name);self.db=self.folder/'test.sqlite3';initialize(self.db)
        self.app=Application(self.db,Answer,self.folder/'traces')
        self.token=self.app.start({'user':'U001','company':'C001','month':'2026-09'})['token']

    def test_scope_and_readonly(self):
        data=self.app.call(self.token,'state',{})
        self.assertEqual('9622.06',data['totals']['invoice_total']);self.assertEqual(10,len(data['invoices']))
        self.assertNotIn('C002',[r['company_id'] for r in data['rules']])
        with self.assertRaises(BusinessError):self.app.start({'user':'U002','company':'C002'})
        token=self.app.start({'user':'U002','company':'C001'})['token']
        self.assertFalse(self.app.call(token,'state',{})['can_write'])

    def test_confirm_and_stale_button(self):
        chat=self.app.sessions[self.token]['chat']
        chat.dispatch('prepare_update',{'invoice_id':'F002','changes':{'purpose':'网页用户提供'}})
        draft=self.app.call(self.token,'state',{})['pending']
        with self.assertRaises(BusinessError):self.app.call(self.token,'confirm',{'operation_id':'wrong'})
        self.assertEqual('',Service(self.db).invoice('U001','C001','F002')['purpose'])
        result=self.app.call(self.token,'confirm',{'operation_id':draft['operation_id']})
        self.assertIn('已保存',result['reply'])
        self.assertEqual('网页用户提供',Service(self.db).invoice('U001','C001','F002')['purpose'])
        with self.assertRaises(BusinessError):self.app.call(self.token,'confirm',{'operation_id':draft['operation_id']})

    def test_preference_buttons_and_session_close(self):
        self.app.call(self.token,'preference',{'key':'style','value':'简洁'})
        self.assertEqual('简洁',self.app.call(self.token,'state',{})['memory']['preferences'][0]['value'])
        self.app.call(self.token,'preference',{'key':'style','delete':True})
        self.assertEqual([],self.app.call(self.token,'state',{})['memory']['preferences'])
        self.app.call(self.token,'close',{})
        with self.assertRaises(BusinessError):self.app.call(self.token,'state',{})

    def test_parallel_requests_rejected(self):
        lock=self.app.sessions[self.token]['lock'];lock.acquire()
        try:
            with self.assertRaises(BusinessError) as error:self.app.call(self.token,'state',{})
            self.assertEqual('session_busy',error.exception.code)
        finally:lock.release()

    def test_failed_model_clears_draft_and_no_save(self):
        chat=self.app.sessions[self.token]['chat']
        chat.dispatch('prepare_update',{'invoice_id':'F002','changes':{'purpose':'旧草稿'}})
        with patch.object(chat.model,'chat',side_effect=BusinessError('model_unavailable','模型暂时离线')):
            with self.assertRaises(BusinessError):self.app.call(self.token,'chat',{'text':'继续查询'})
        self.assertIsNone(chat.pending)
        self.assertEqual('',Service(self.db).invoice('U001','C001','F002')['purpose'])
        self.assertIn('具体',self.app.call(self.token,'chat',{'text':'恢复后查询'})['reply'])

    def test_saved_data_not_reported_failed_if_memory_refresh_fails(self):
        chat=self.app.sessions[self.token]['chat']
        chat.dispatch('prepare_update',{'invoice_id':'F002','changes':{'purpose':'应保存'}})
        with patch.object(chat.memory,'refresh',side_effect=BusinessError('rule_missing','当前规则不可用')):
            reply=chat.turn('/confirm')
        self.assertIn('保存已完成',reply);self.assertIn('任务刷新失败',reply)
        self.assertEqual('应保存',Service(self.db).invoice('U001','C001','F002')['purpose'])

    def test_long_dialogue_keeps_task_and_bounds_context(self):
        chat=self.app.sessions[self.token]['chat']
        chat.dispatch('check',{'month':'2026-09'})
        captured=[]
        def model(messages,tools):
            captured.append(messages);return {'role':'assistant','content':'好的，已了解。'}
        with patch.object(chat.model,'chat',side_effect=model):
            for i in range(20):chat.turn('补充交流'+str(i))
        self.assertLessEqual(len(chat.turns),8)
        self.assertEqual(10,len(captured[-1])) # system + 4 pairs + current user
        self.assertIn('2026-09',captured[-1][0]['content'])
        self.assertIn('F002',captured[-1][0]['content'])
        self.assertNotIn('补充交流0',json.dumps(captured[-1],ensure_ascii=False))


class HTTPTests(unittest.TestCase):
    setUp=WebTests.setUp
    # 真实HTTP只运行本类专有测试，复用临时库准备。
    def test_http_origin_and_path_validation(self):
        server=make_server(self.app,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{server.server_port}'
        with urlopen(url,timeout=5) as r:
            self.assertEqual(200,r.status);self.assertIn('财税助手',r.read().decode());self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
        headers={'Content-Type':'application/json','X-Harness-Client':'local-ui','Origin':'https://untrusted.example'}
        req=Request(url+'/api/start',data=b'{}',headers=headers)
        with self.assertRaises(HTTPError) as e:urlopen(req,timeout=5)
        self.assertEqual(403,e.exception.code)
        e.exception.close()
        headers['Origin']=url
        req=Request(url+'/api/state',data=b'{}',headers={**headers,'Authorization':'Bearer '+self.token})
        with urlopen(req,timeout=5) as r:self.assertTrue(json.load(r)['ok'])
        with self.assertRaises(HTTPError) as missing:urlopen(url+'/../data/business.sqlite3',timeout=5)
        missing.exception.close()
