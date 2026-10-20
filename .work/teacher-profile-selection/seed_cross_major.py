import httpx
with httpx.Client(base_url='http://localhost:8000',trust_env=False,timeout=30) as c:
    r=c.post('/api/debug/session',json={'role':'admin'});r.raise_for_status()
    h={'Authorization':'Bearer '+r.json()['access_token']}
    def call(method,url,**kw):
        r=c.request(method,url,headers=h,**kw)
        if r.is_error:raise RuntimeError(f'{url}: {r.status_code} {r.text}')
        return r.json()
    major='插画设计（演示）';name='[跨专业演示] 插画设计 · 第二学期（虚构数据）'
    plans=call('GET','/api/planning/plans');p=next((p for p in plans if p['name']==name),None)
    if p is None:
        docs=call('GET','/api/planning/curricula');doc=next((d for d in docs if d['major']==major and d['cohort']=='2026'),None)
        if not doc:
            content='课程编码,课程名称,学分,总学时,上课学期,课程性质,专业方向,领域标签\nDEMO-ILL-101,【跨专业演示】插画专题,1,8,2,专业必修课,插画设计,插画\n'
            doc=call('POST','/api/planning/curricula/import',data={'major':major,'cohort':'2026','revision':1},files={'file':('fictional-illustration.csv',content.encode(),'text/csv')})
        call('POST',f"/api/planning/curricula/{doc['id']}/activate")
        p=call('POST','/api/planning/plans',json={'name':name,'major':major,'cohort':'2026','semester':2,'groups':['演示插画2601'],'start_date':'2027-02-01','weeks':20,'deadline':'2027-01-31T23:59:00','rule_confirmed':True})
    base=f"/api/planning/plans/{p['id']}";state=call('GET',base)
    if state['state']=='draft':
        call('POST',base+'/generate');state=call('GET',base)
        for task in state['tasks']:
            allowed=['name','code','group','class_name','student_ids','department','credits','required_hours','direction','tags','source','teacher_count','student_count','mode','room_type','tail_weeks']
            data={k:task[k] for k in allowed if k in task}
            data.update(start_week=5,end_week=6,slots=[{'day':5,'start':1,'count':4}],room_id=1,profile_verified=True)
            call('PUT',base+f"/tasks/{task['id']}",json=data)
        call('POST',base+'/open')
    print('Cross-major fictional curriculum/plan ready:',p['id'])
