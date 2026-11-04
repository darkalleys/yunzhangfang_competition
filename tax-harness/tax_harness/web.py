"""本机演示服务。复用业务工具，不提供远程部署或账号认证。"""
from collections import deque
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from .chat import ChatSession, Ollama
from .service import Service,authorize,month_bounds,public_invoice
from .store import BusinessError,DEFAULT_DB,connect

STATIC=Path(__file__).parent/'static'


class Application:
    def __init__(self,db=DEFAULT_DB,model_factory=Ollama,trace_dir=None):
        self.db,self.model_factory,self.trace_dir=db,model_factory,trace_dir
        self.sessions={};self.guard=threading.Lock()

    def start(self,data):
        user,company,month=data.get('user'),data.get('company'),data.get('month')
        chat=ChatSession(user,company,self.db,self.model_factory(),month or None,trace_dir=self.trace_dir)
        token=secrets.token_urlsafe(32)
        with self.guard:
            expired=[k for k,v in self.sessions.items() if time.monotonic()-v['used']>7200]
            for k in expired:self.sessions.pop(k,None)
            if len(self.sessions)>=64:raise BusinessError('session_limit','会话过多，请关闭旧会话或重新启动服务。')
            self.sessions[token]={'chat':chat,'lock':threading.Lock(),'used':time.monotonic()}
        return {'token':token,'user':user,'company':company,'month':chat.month,'restored':chat.memory.snapshot()}

    def call(self,token,action,data):
        with self.guard: entry=self.sessions.get(token)
        if not entry or time.monotonic()-entry['used']>7200:
            raise BusinessError('session_missing','会话已失效，请重新进入。')
        if not entry['lock'].acquire(blocking=False):raise BusinessError('session_busy','该会话正在处理，请等待完成。')
        try:
            entry['used']=time.monotonic();chat=entry['chat']
            if action=='close':
                chat.pending=None
                with self.guard:self.sessions.pop(token,None)
                return {'closed':True}
            if action=='chat':
                reply=chat.turn(data.get('text'))
                return {'reply':reply,'pending':self.draft(chat)}
            if action=='confirm':
                # 确认必须匹配用户当前看到的草稿，不能确认后来出现的另一个草稿。
                if not chat.pending or data.get('operation_id')!=chat.pending['operation_id']:
                    raise BusinessError('stale_draft','草稿已失效，请重新查看。')
                return {'reply':chat.turn('/confirm'),'pending':None}
            if action=='cancel':return {'reply':chat.turn('/cancel'),'pending':None}
            if action=='preference':
                chat.pending=None
                result=chat.memory.preference(data.get('key'),None if data.get('delete') is True else data.get('value'))
                chat.record('ui_preference',key=data.get('key'),deleted=data.get('delete') is True)
                return result
            if action=='task-clear':
                chat.pending=None;return chat.memory.clear_task()
            if action=='state':return self.state(chat,data.get('month') or chat.month or '2026-09')
            if action=='trace':
                if not chat.trace_path.exists():return {'events':[]}
                with chat.trace_path.open(encoding='utf-8') as f: lines=deque(f,maxlen=60)
                return {'events':[json.loads(x) for x in lines]}
            raise BusinessError('unknown_action','不支持的操作。')
        finally:entry['lock'].release()

    @staticmethod
    def draft(chat):
        if not chat.pending:return None
        return {k:chat.pending[k] for k in ('invoice_id','changes','operation_id')}

    def state(self,chat,month):
        start,end=month_bounds(month)
        with connect(self.db) as con:
            authorize(con,chat.user,chat.company)
            invoices=[public_invoice(r) for r in con.execute('SELECT * FROM invoices WHERE company_id=? AND invoice_date>=? AND invoice_date<? ORDER BY invoice_id',(chat.company,start,end))]
            bank=[dict(r) for r in con.execute('SELECT * FROM bank_records WHERE company_id=? AND transaction_date>=? AND transaction_date<? ORDER BY transaction_date,record_id',(chat.company,start,end))]
            rules=[dict(r) for r in con.execute('SELECT * FROM rules WHERE company_id=? OR company_id IS NULL ORDER BY rule_id,effective_date',(chat.company,))]
            permission=con.execute('SELECT can_write FROM permissions WHERE user_id=? AND company_id=?',(chat.user,chat.company)).fetchone()[0]
        return {'month':month,'totals':chat.service.totals(chat.user,chat.company,month),'invoices':invoices,'bank':bank,'rules':rules,
                'memory':chat.memory.snapshot(),'pending':self.draft(chat),'audit':chat.service.audit(chat.user,chat.company),'can_write':bool(permission)}


def make_server(app,port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass

        def send(self,status,body,kind='application/json; charset=utf-8'):
            encoded=json.dumps(body,ensure_ascii=False).encode() if isinstance(body,dict) else body
            self.send_response(status)
            self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(encoded)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(encoded)

        def local(self):
            allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            host=self.headers.get('Host','')
            origin=self.headers.get('Origin')
            return host in allowed and (not origin or origin in {'http://'+h for h in allowed})

        def do_GET(self):
            if not self.local():return self.send(403,{'ok':False,'error':'仅支持本机访问。'})
            files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/app.css':('app.css','text/css; charset=utf-8')}
            item=files.get(self.path)
            if not item:return self.send(404,{'ok':False,'error':'页面不存在。'})
            return self.send(200,(STATIC/item[0]).read_bytes(),item[1])

        def do_POST(self):
            if not self.local() or self.headers.get('X-Harness-Client')!='local-ui' or self.headers.get_content_type()!='application/json':
                return self.send(403,{'ok':False,'error':'请求来源无效。'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>24000:raise ValueError('请求长度无效。')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('请求必须为对象。')
                if self.path=='/api/start':result=app.start(data)
                elif self.path.startswith('/api/'):
                    token=self.headers.get('Authorization','').removeprefix('Bearer ')
                    result=app.call(token,self.path[5:],data)
                else:raise BusinessError('unknown_action','接口不存在。')
                self.send(200,{'ok':True,'data':result})
            except (BusinessError,ValueError,TypeError,sqlite3.Error,OSError) as exc:
                code=getattr(exc,'code','request_error')
                self.send(409 if code in ('session_busy','stale_draft') else 400,{'ok':False,'error':str(exc),'code':code})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(db=DEFAULT_DB,port=8765):
    if not 1<=port<=65535:raise ValueError('端口范围为1至65535。')
    app=Application(db)
    server=make_server(app,port)
    print(f'本地演示页面：http://127.0.0.1:{port} （Ctrl+C停止）',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
