from pathlib import Path
import hashlib
import json
import sqlite3
import httpx

root=Path(__file__).resolve().parents[2]
with sqlite3.connect('/private/tmp/scheduling-demo-20261020.db') as source, sqlite3.connect(root/'.work/import-word-export/demo-before-import-export.db') as target:source.backup(target)
with httpx.Client(base_url='http://localhost:8000',trust_env=False,timeout=30) as client:
    def auth(role,teacher=None):
        r=client.post('/api/debug/session',json={'role':role,'teacher_id':teacher});r.raise_for_status();return {'Authorization':'Bearer '+r.json()['access_token']}
    admin=auth('admin');teacher=auth('teacher',1)
    def call(method,url,headers=admin,**kwargs):
        r=client.request(method,url,headers=headers,**kwargs)
        if r.is_error:raise RuntimeError(f'{method} {url}: {r.status_code} {r.text}')
        return r.json()
    original=Path('/Users/tangwang/Desktop/王刚/知识库V2/10_原始资料/教学/26人才培养方案/0101视觉传达设计专业人才培养方案(1).docx')
    content=original.read_bytes();sha=hashlib.sha256(content).hexdigest()
    docs=call('GET','/api/planning/curricula');doc=next((d for d in docs if d['sha256']==sha),None)
    if doc is None:
        revision=1+max((d['revision'] for d in docs if d['major']=='视觉传达设计' and d['cohort']=='2026'),default=0)
        doc=call('POST','/api/planning/curricula/import',data={'major':'视觉传达设计','cohort':'2026','revision':revision},files={'file':(original.name,content,'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
    print('LIVE IMPORT',doc['id'],len(doc['rows']),'rows; active:',doc['active'])
    name='[导出演示] 学院Word模板 · 虚构数据'
    plans=call('GET','/api/planning/plans');plan=next((p for p in plans if p['name']==name),None)
    if plan is None:
        plan=call('POST','/api/planning/plans',json={'name':name,'major':'视觉传达设计','cohort':'2026','semester':1,'groups':['导出演示班01','导出演示班02'],'start_date':'2027-09-06','weeks':20,'deadline':'2027-08-31T23:59:00','rule_confirmed':True})
    pid=plan['id'];base=f'/api/planning/plans/{pid}'
    state=call('GET',base)
    if state['state']=='draft':
        for group,start in [('导出演示班01',1),('导出演示班02',5)]:
            for code,label,day in [('DEMO-EXPORT-A','【演示】文字与版式设计',1),('DEMO-EXPORT-B','【演示】品牌视觉设计',3)]:
                if any(t['code']==code and t['group']==group for t in state['tasks']):continue
                call('POST',base+'/tasks',json={'name':label,'code':code,'group':group,'department':'视觉传达设计','credits':2,'required_hours':16,'start_week':1,'end_week':4,'direction':'视觉传达设计','tags':['版式'],'profile_verified':True,'teacher_count':1,'student_count':30,'room_id':1,'slots':[{'day':day,'start':start,'count':4}]})
        call('POST',base+'/open');state=call('GET',base)
    if state['state']=='open':
        own=call('GET',base,headers=teacher)
        draft=call('PUT',base+'/draft',headers=teacher,json={'revision':own['draft']['revision'],'plan_revision':own['revision'],'task_ids':[t['id'] for t in own['tasks']]})
        call('POST',base+'/submit',headers=teacher,json={'revision':draft['revision']})
        call('POST',base+'/match');state=call('GET',base)
    if state['state']=='matched':
        for task in state['tasks']:
            if not task['locked']:call('POST',base+'/assign',json={'task_id':task['id'],'teacher_ids':[1],'match_id':state['match']['id'],'reason':'仅用于虚构演示数据的Word导出验证'})
        call('POST',base+'/publish')
    r=client.get('/api/planning/exports/word',headers=admin,params={'major':'视觉传达设计','start_date':'2027-09-06','weeks':20});r.raise_for_status()
    (root/'.work/import-word-export/api-export-sample.docx').write_bytes(r.content)
    print('LIVE EXPORT',pid,len(r.content),'bytes; original unchanged:',hashlib.sha256(original.read_bytes()).hexdigest()==sha)
