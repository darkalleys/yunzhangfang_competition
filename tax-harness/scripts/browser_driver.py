"""Windows Edge本地验收驱动，仅依赖标准库；通过DevTools协议查看实际页面。"""
import base64
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import urlopen


class Browser:
    def __init__(self,url,profile):
        binary=Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
        if not binary.exists():raise RuntimeError('浏览器验收需要已安装的Microsoft Edge。')
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        self.process=subprocess.Popen([str(binary),'--headless','--disable-gpu','--no-first-run','--no-default-browser-check',f'--remote-debugging-port={port}',f'--user-data-dir={profile}',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.sock=None;self.counter=0;self.errors=[]
        try:
            for _ in range(100):
                try:
                    with urlopen(f'http://127.0.0.1:{port}/json',timeout=1) as response: pages=json.load(response)
                    page=next((p for p in pages if p.get('type')=='page'),None)
                    if page:break
                except OSError:pass
                time.sleep(.1)
            else:raise RuntimeError('浏览器启动超时。')
            address=urlsplit(page['webSocketDebuggerUrl']);self.sock=socket.create_connection((address.hostname,address.port),10);self.sock.settimeout(120)
            key=base64.b64encode(os.urandom(16)).decode()
            request=f'GET {address.path} HTTP/1.1\r\nHost: {address.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'
            self.sock.sendall(request.encode());header=b''
            while not header.endswith(b'\r\n\r\n'):header+=self.sock.recv(1)
            if b' 101 ' not in header:raise RuntimeError('DevTools连接失败。')
            self.call('Runtime.enable');self.call('Page.enable')
            self.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
        except Exception:
            self.close();raise

    def read(self,n):
        data=b''
        while len(data)<n:
            part=self.sock.recv(n-len(data))
            if not part:raise RuntimeError('浏览器连接中断。')
            data+=part
        return data

    def receive(self):
        a,b=self.read(2);length=b&127
        if length==126:length=struct.unpack('!H',self.read(2))[0]
        elif length==127:length=struct.unpack('!Q',self.read(8))[0]
        mask=self.read(4) if b&128 else None
        payload=self.read(length)
        if mask:payload=bytes(v^mask[i%4] for i,v in enumerate(payload))
        if a&15==8:raise RuntimeError('浏览器连接已关闭。')
        return json.loads(payload)

    def call(self,method,params=None):
        self.counter+=1;ident=self.counter
        payload=json.dumps({'id':ident,'method':method,'params':params or {}}).encode();length=len(payload);mask=os.urandom(4)
        header=bytes([0x81,0x80|length]) if length<126 else bytes([0x81,0x80|126])+struct.pack('!H',length) if length<65536 else bytes([0x81,0x80|127])+struct.pack('!Q',length)
        self.sock.sendall(header+mask+bytes(x^mask[i%4] for i,x in enumerate(payload)))
        while True:
            message=self.receive()
            if message.get('method')=='Runtime.exceptionThrown':self.errors.append(message)
            if message.get('id')==ident:
                if 'error' in message:raise RuntimeError(str(message['error']))
                return message.get('result',{})

    def evaluate(self,expression):
        result=self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
        if 'exceptionDetails' in result:raise RuntimeError(str(result['exceptionDetails']))
        return result.get('result',{}).get('value')

    def wait(self,expression,timeout=120):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            if self.evaluate(expression):return
            time.sleep(.15)
        raise RuntimeError('等待页面状态超时：'+expression)

    def screenshot(self,path):
        result=self.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
        Path(path).write_bytes(base64.b64decode(result['data']))

    def close(self):
        if self.sock:
            try:self.call('Browser.close')
            except (OSError,RuntimeError,ValueError):pass
            self.sock.close();self.sock=None
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
