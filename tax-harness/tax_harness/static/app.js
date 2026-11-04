'use strict';
const $=id=>document.getElementById(id);
let token=null, pending=null, busy=false;
const controls=['send','prompt','refresh','pref-save','clear-task','load-trace','confirm','cancel'];
function status(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
function enabled(){controls.forEach(id=>$(id).disabled=!token||busy);document.querySelectorAll('[data-quick],#preferences button').forEach(b=>b.disabled=!token||busy);['connect','user','company','month'].forEach(id=>$(id).disabled=busy);}
async function api(action,data={}){
  const headers={'Content-Type':'application/json','X-Harness-Client':'local-ui'};
  if(token)headers.Authorization='Bearer '+token;
  const response=await fetch('/api/'+action,{method:'POST',headers,body:JSON.stringify(data)});
  const body=await response.json();if(!body.ok)throw new Error(body.error||'请求失败');return body.data;
}
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function message(text,type='assistant'){
  $('messages').querySelector('.welcome')?.remove();const n=el('div',undefined,'message '+type);
  n.append(el('small',type==='user'?'你':type==='error'?'处理提示':'财税助手'),document.createTextNode(text));$('messages').append(n);$('messages').scrollTop=$('messages').scrollHeight;
}
function draft(value){pending=value;$('draft').hidden=!value;if(value)$('draft-text').textContent='发票 '+value.invoice_id+'\n'+Object.entries(value.changes).map(([k,v])=>(k==='purpose'?'用途':'备注')+'：'+v).join('\n');}
function table(container,columns,rows){
  container.replaceChildren();if(!rows.length){container.append(el('p','当前月份没有记录','empty'));return;}
  const t=el('table'),head=el('tr'),thead=el('thead'),tbody=el('tbody');
  columns.forEach(([name])=>head.append(el('th',name)));thead.append(head);t.append(thead);
  rows.forEach(row=>{const tr=el('tr');columns.forEach(([,fn])=>tr.append(el('td',fn(row))));tbody.append(tr);});t.append(tbody);container.append(t);
}
function render(data){
  $('invoice-total').textContent=data.totals.invoice_total;$('income-total').textContent=data.totals.bank_income;$('expense-total').textContent=data.totals.bank_expense;
  $('invoice-count').textContent=data.month+' · '+data.totals.invoice_count+' 张发票';
  $('identity').textContent=$('company').selectedOptions[0].text+' · '+(data.can_write?'可修改用途及备注':'仅查看');
  table($('invoices'),[['编号',r=>r.invoice_id],['日期',r=>r.invoice_date],['金额',r=>r.amount],['用途',r=>r.purpose||'（未填写）'],['备注',r=>r.remark||'—']],data.invoices);
  table($('bank'),[['日期',r=>r.transaction_date],['方向',r=>r.direction],['金额',r=>(r.amount_cents/100).toFixed(2)],['对方',r=>r.counterparty]],data.bank);
  const task=data.memory.task;$('task').replaceChildren(el('div',task?task.month+' · 待补用途 '+task.missing_ids.length+' 张\n'+task.missing_ids.join('、'):'没有未完成的用途检查任务',task?'task-value':'empty'));
  $('preferences').replaceChildren();
  if(!data.memory.preferences.length)$('preferences').append(el('p','尚未设置明确偏好','empty'));
  data.memory.preferences.forEach(p=>{const row=el('div',undefined,'preference'),text=el('div',p.key+'：'+p.value),button=el('button','删除','secondary small');button.type='button';button.disabled=busy;button.onclick=()=>work(async()=>{await api('preference',{key:p.key,delete:true});status('偏好已删除');});row.append(text,button);$('preferences').append(row);});
  $('rules').replaceChildren();data.rules.forEach(r=>{const row=el('article',undefined,'rule');row.append(el('strong',r.name+' · '+r.version+'版'),document.createTextNode(' '),el('span',r.status==='active'?'启用':'已停用',r.status==='active'?'pill':'pill off'),el('p',r.text),el('small',r.rule_id+' · 生效 '+r.effective_date));$('rules').append(row);});
  $('audit').replaceChildren();if(!data.audit.operations.length)$('audit').append(el('p','当前企业尚无修改记录','empty'));
  data.audit.operations.forEach(a=>{const d=el('details');d.append(el('summary',a.invoice_id+' · '+a.user_id+' · '+a.created_at),el('pre',JSON.stringify({修改内容:a.changes,修改前:a.before,回读结果:a.after},null,2)));$('audit').append(d);});draft(data.pending);
}
async function refresh(){if(token)render(await api('state',{month:$('month').value}));}
function reset(){token=null;draft(null);$('messages').replaceChildren();$('trace').replaceChildren();['invoices','bank','task','preferences','rules','audit'].forEach(id=>$(id).replaceChildren());['invoice-total','income-total','expense-total'].forEach(id=>$(id).textContent='—');$('invoice-count').textContent='当前月份';$('identity').textContent='尚未进入会话';}
async function work(fn){if(busy)return;busy=true;enabled();try{await fn();}catch(e){status(e.message,true);message(e.message,'error');}finally{try{await refresh();}catch(e){status(e.message,true);}busy=false;enabled();}}
async function send(text){if(!token||!text.trim())return;await work(async()=>{message(text,'user');$('prompt').value='';status('助手正在查询和处理，请稍候…');const r=await api('chat',{text});message(r.reply);draft(r.pending);status(r.pending?'草稿尚未保存，请核对后确认。':'处理完成，已刷新当前数据。');});}
$('connection').onsubmit=async e=>{e.preventDefault();if(busy)return;await work(async()=>{
  try{if(token)await api('close');}finally{reset();}
  const r=await api('start',{user:$('user').value,company:$('company').value,month:$('month').value});token=r.token;
  message(r.restored.task?'已恢复未完成任务，并重新查询最新进度。请选择继续检查或提出新的需求。':'会话已就绪。可以查询金额、检查用途或补充发票资料。');status('会话已建立；当前月份 '+r.month);
});};
['user','company','month'].forEach(id=>$(id).onchange=()=>work(async()=>{try{if(token)await api('close');}finally{reset();}status('范围已变更，请点击进入会话。');}));
$('chat-form').onsubmit=e=>{e.preventDefault();send($('prompt').value);};
$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send($('prompt').value);}};
document.querySelectorAll('[data-quick]').forEach(b=>b.onclick=()=>{const m=$('month').value;const q={totals:`查询${m}的发票总额、银行收入和支出。`,check:`检查${m}哪些发票必须补用途，并说明规则依据。`,resume:'继续上次未完成的用途检查，重新查询最新缺项。'};send(q[b.dataset.quick]);});
$('confirm').onclick=()=>work(async()=>{const r=await api('confirm',{operation_id:pending.operation_id});message(r.reply);draft(null);status('已处理保存请求，以下显示实际回读结果。');});
$('cancel').onclick=()=>work(async()=>{const r=await api('cancel');message(r.reply);draft(null);status('草稿已取消。');});
$('refresh').onclick=()=>work(async()=>status('已重新读取当前数据。'));
$('clear-task').onclick=()=>work(async()=>{await api('task-clear');status('任务记录已删除，已保存的发票内容保留。');});
$('pref-form').onsubmit=e=>{e.preventDefault();work(async()=>{await api('preference',{key:$('pref-key').value,value:$('pref-value').value});$('pref-key').value='';$('pref-value').value='';status('偏好已保存，后续回答会载入。');});};
$('load-trace').onclick=()=>work(async()=>{const r=await api('trace');$('trace').replaceChildren();r.events.forEach(event=>{const d=el('details');d.append(el('summary',event.event+' · '+event.time_utc),el('pre',JSON.stringify(event,null,2)));$('trace').append(d);});status('已载入本会话最近运行记录。');});
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(t=>{t.setAttribute('aria-selected',t===b?'true':'false');$('panel-'+t.dataset.tab).hidden=t!==b;});});
enabled();
