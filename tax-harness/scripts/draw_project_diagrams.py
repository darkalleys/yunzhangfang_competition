"""生成可维护的SVG架构图与调用链路图；文字和连线均为代码原生矢量。"""
from pathlib import Path
from xml.etree.ElementTree import Element,SubElement,ElementTree

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'/'understanding'/'figures'
GREEN='#176b53';INK='#183a39';BLUE='#326587';PURPLE='#6d5594';AMBER='#a67320'


class Figure:
    def __init__(self,title,subtitle,width,height):
        self.root=Element('svg',{'xmlns':'http://www.w3.org/2000/svg','width':str(width),'height':str(height),'viewBox':f'0 0 {width} {height}','role':'img'})
        SubElement(self.root,'title').text=title
        SubElement(self.root,'desc').text=subtitle
        self.rect(0,0,width,height,'#f4f7f3',0)
        defs=SubElement(self.root,'defs')
        for color in [GREEN,BLUE,PURPLE,AMBER]:
            marker=SubElement(defs,'marker',{'id':'a'+color[1:],'viewBox':'0 0 10 10','refX':'9','refY':'5','markerWidth':'7','markerHeight':'7','orient':'auto-start-reverse'})
            SubElement(marker,'path',{'d':'M 0 0 L 10 5 L 0 10 z','fill':color})
        self.text(40,44,title,27,INK)
        self.text(40,76,subtitle,14,'#627a71')

    def rect(self,x,y,w,h,fill='#fff',radius=13,stroke='#d6e2da'):
        return SubElement(self.root,'rect',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'rx':str(radius),'fill':fill,'stroke':stroke})

    def text(self,x,y,text,size=15,color=INK,anchor='start'):
        node=SubElement(self.root,'text',{'x':str(x),'y':str(y),'fill':color,'font-size':str(size),'font-family':'Microsoft YaHei, Segoe UI, sans-serif','text-anchor':anchor})
        for i,line in enumerate(text.split('\n')):
            SubElement(node,'tspan',{'x':str(x),'dy':str(0 if i==0 else size*1.6)}).text=line
        return node

    def box(self,x,y,w,h,title,lines,fill='#fff'):
        self.rect(x,y,w,h,fill);self.text(x+18,y+30,title,18)
        self.text(x+18,y+57,lines,14,'#50695e')

    def edge(self,points,label='',x=0,y=0,color=GREEN,both=False,dashed=False):
        args={'d':'M '+' L '.join(f'{a} {b}' for a,b in points),'fill':'none','stroke':color,'stroke-width':'2','marker-end':'url(#a'+color[1:]+')'}
        if both:args['marker-start']='url(#a'+color[1:]+')'
        if dashed:args['stroke-dasharray']='5 5'
        SubElement(self.root,'path',args)
        if label:self.text(x,y,label,13,color)

    def save(self,name):
        OUT.mkdir(parents=True,exist_ok=True)
        ElementTree(self.root).write(OUT/name,encoding='utf-8',xml_declaration=True)


def architecture():
    f=Figure('财税助手实际架构','代码基线 bab7940 / 0.4.0 · 只有自然语言分支调用 qwen3:8b · 双向线表示请求与返回',1280,1120)
    f.box(40,120,350,105,'浏览器用户','选择用户、企业和月份\n自然语言、确认按钮、资料面板')
    f.box(450,120,350,105,'终端对话用户','chat进入自然语言处理\n显式偏好与任务控制命令')
    f.box(860,120,350,105,'结构化CLI与本地维护','menu / 业务命令 / manage.py\ninit / migrate / backup.py')
    f.box(40,325,350,140,'web.py / Application','本机HTTP · 来源和会话校验\n固定身份与企业 · 会话锁\n按钮分支直接调用程序工具')
    f.box(450,325,350,140,'chat.py / ChatSession','上下文：身份、月份、最近对话\n读取任务偏好 · 模型工具循环\n保存草稿、确认与错误处理')
    f.box(860,325,350,140,'程序直达与维护模块','Service：结构化业务CLI\nknowledge/state：规则、记忆、迁移\nmaintenance/store：备份、导入')
    f.box(40,570,350,130,'Ollama / qwen3:8b','本机11434端口 /api/chat\n理解、工具请求和回答生成\nbge-m3未接入；无独立检测模型','#f0ecf7')
    f.box(450,570,350,130,'业务工具与程序校验','Service：totals/check/invoice/update\nChatSession.dispatch：rules/prepare\nprepare_update仅生成内存草稿')
    f.box(860,570,350,130,'state.py / Memory','每个用户、企业一个活动任务\n显式偏好管理 · 当前数据复查\n不保存草稿或修改授权')
    f.box(40,840,350,135,'JSONL运行记录','实际模型输入、输出与工具结果\n选用记忆、规则、保存回读\n日志不是自动载入的会话记忆')
    f.box(450,840,350,135,'SQLite / 业务与规则','企业、用户、权限、发票、流水\nrules / audit_log / metadata\n金额用整数分，发票按企业定位')
    f.box(860,840,350,135,'SQLite / 任务与偏好','tasks / preferences\nstate_events / rule_events\n与业务表位于同一数据库文件')
    f.edge([(215,225),(215,325)],'HTTP / JSON',230,280,both=True)
    f.edge([(390,390),(450,390)],color=GREEN,both=True)
    f.edge([(390,445),(400,445),(400,560),(470,560),(470,570)],'按钮直达工具',420,550,both=True,dashed=True)
    f.edge([(625,225),(625,325)],'自然语言',640,280,both=True)
    f.edge([(1035,225),(1035,325)],'显式管理',1050,280,both=True)
    f.edge([(450,440),(415,440),(415,540),(215,540),(215,570)],'模型请求 / 工具请求 / 文本',55,520,PURPLE,True)
    f.edge([(625,465),(625,570)],'工具分发 / 结果',640,525,both=True)
    f.edge([(800,425),(830,425),(830,520),(1035,520),(1035,570)],'记忆载入 / 进度刷新',895,505,both=True)
    f.edge([(625,700),(625,840)],'授权查询 / 事务保存',640,777,BLUE,True)
    f.edge([(1035,700),(1035,840)],'读写任务、偏好与事件',890,777,AMBER,True)
    f.edge([(450,455),(440,455),(440,745),(20,745),(20,910),(40,910)],color=GREEN,dashed=True)
    f.edge([(1210,395),(1240,395),(1240,1020),(625,1020),(625,975)],'规则管理、迁移、备份也直接访问数据库，不调用模型',690,1045,BLUE)
    f.text(40,1088,'返回：工具结果交回同一个模型组织回答；确认保存、资料刷新和偏好按钮由程序直接返回。',16)
    f.text(40,1110,'业务与状态框表示同一business.sqlite3的不同表；JSONL为独立文件。',13)
    f.save('architecture.svg')


def sequence(name,title,steps):
    f=Figure(title,'紫色：模型调用   绿色：程序调用   蓝色：数据读取   金色：状态写入 · 这里展示一种成功路径，模型调用次数可变化',1280,180+len(steps)*74)
    xs=[110,365,620,875,1130]
    labels=['用户 / 浏览器','Application / ChatSession','Ollama / qwen3:8b','Service / Memory','SQLite / 内存 / JSONL']
    for x,label in zip(xs,labels):
        f.rect(x-100,100,200,45,'#fff',8);f.text(x,128,label,13,INK,'middle')
        SubElement(f.root,'path',{'d':f'M {x} 147 V {160+len(steps)*74}','stroke':'#ccd9d0','stroke-dasharray':'5 5'})
    for i,(a,b,label,color) in enumerate(steps):
        y=180+i*74
        if a is None:
            f.rect(35,y-20,1210,49,'#e9f0e7',7);f.text(55,y+10,label,14,color)
        else:
            f.edge([(xs[a],y+23),(xs[b],y+23)],color=color)
            center=(xs[a]+xs[b])/2
            lines=label.split('\n');width=min(1180,max(len(x) for x in lines)*12+32)
            f.rect(max(25,min(center-width/2,1255-width)),y-29,width,48,'#f4f7f3',3,'none')
            f.text(center,y-9,f'{i+1:02d}  '+label,13,color,'middle')
    f.save(name)


def main():
    architecture()
    sequence('query-chain.svg','调用链 A：检查缺项并返回依据',[
        (0,1,'POST /api/chat：检查2026年9月用途缺项',GREEN),
        (1,4,'读 tasks、preferences；构建本轮上下文',BLUE),
        (1,2,'第1次模型请求：system + 记忆 + 最近对话 + tools',PURPLE),
        (2,1,'返回 tool_call：check(month="2026-09")',PURPLE),
        (1,3,'校验月份来源，固定注入 U001 / C001',GREEN),
        (3,4,'读 permissions、启用规则及当前 invoices',BLUE),
        (4,3,'返回五张缺项与 R002 2.0 版',BLUE),
        (3,1,'返回结构化检查结果，不修改发票',GREEN),
        (1,4,'Memory.track：写 tasks / state_events',AMBER),
        (1,2,'第2次模型请求：加入 role=tool 的实际结果',PURPLE),
        (2,1,'返回解释、缺项编号及依据',PURPLE),
        (1,0,'JSON：reply、pending；浏览器展示回答',GREEN),
        (0,1,'随后 POST /api/state 刷新资料面板',GREEN),
        (1,4,'直接读当前资料和任务快照，不再调用模型',BLUE),
        (None,None,'每轮持续追加JSONL；totals查询本身不创建任务，check才调用Memory.track。',INK)])
    sequence('save-chain.svg','调用链 B：提出修改、确认、事务保存与回读',[
        (0,1,'POST /api/chat：F002用途填为员工培训资料打印',GREEN),
        (1,2,'模型理解目标、字段和用户明确给出的内容',PURPLE),
        (2,1,'tool_call：prepare_update(invoice_id, changes)',PURPLE),
        (1,3,'校验内容来源、字段白名单、权限并读取原发票',GREEN),
        (1,4,'仅写 pending 内存草稿；并追加运行日志',AMBER),
        (1,2,'把“草稿未保存”的工具结果交回模型',PURPLE),
        (2,1,'模型生成草稿说明',PURPLE),
        (1,0,'展示草稿及operation_id；此时没有业务UPDATE',GREEN),
        (0,1,'点击确认保存：POST /api/confirm(operation_id)',GREEN),
        (None,None,'以下确认保存分支不调用模型；CLI的/confirm也走同一程序分支。',PURPLE),
        (1,3,'检查草稿编号及快照，调用 Service.update',GREEN),
        (3,4,'BEGIN IMMEDIATE：查权限、幂等编号和原发票',BLUE),
        (3,4,'同一事务：UPDATE invoices + INSERT audit_log',AMBER),
        (None,None,'数据库COMMIT成功之后，才开始业务回读与后续任务刷新。',AMBER),
        (3,4,'新数据库连接 SELECT 当前发票',BLUE),
        (4,3,'返回当前用途、备注及保存状态',BLUE),
        (3,1,'返回已保存与回读结果',GREEN),
        (1,4,'Memory.refresh：重新检查，单独写 tasks / state_events',AMBER),
        (1,0,'程序生成保存结果；若任务刷新失败，明确显示保存已完成',GREEN),
        (None,None,'业务保存事务与任务更新不是同一事务；新会话只恢复任务与偏好，不恢复pending。',INK)])
    print('Generated architecture.svg, query-chain.svg, save-chain.svg:',OUT)


if __name__=='__main__':main()
