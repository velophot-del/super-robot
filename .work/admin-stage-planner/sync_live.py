import httpx
with httpx.Client(base_url='http://localhost:8000',trust_env=False,timeout=30) as c:
 r=c.post('/api/debug/session',json={'role':'admin'});r.raise_for_status();h={'Authorization':'Bearer '+r.json()['access_token']}
 before=c.get('/api/courses/',headers=h,params={'limit':500});before.raise_for_status()
 docs=c.get('/api/planning/curricula',headers=h);docs.raise_for_status()
 for d in docs.json():
  if d['active']:
   r=c.post(f"/api/planning/curricula/{d['id']}/sync-courses",headers=h);r.raise_for_status();print(d['major'],r.json())
 after=c.get('/api/courses/',headers=h,params={'limit':500});after.raise_for_status();print('Library',len(before.json()),'->',len(after.json()),'fractional credits',sum(x['credits']%1!=0 for x in after.json() if x['credits'] is not None))
 plans=c.get('/api/planning/plans',headers=h).json()
 name='[拖拽演示] 视觉传达 · 空白20周班级课表'
 plan=next((p for p in plans if p['name']==name),None)
 if not plan:
  r=c.post('/api/planning/plans',headers=h,json={'name':name,'major':'视觉传达设计','cohort':'2026','semester':1,'groups':['拖拽演示2601','拖拽演示2602'],'start_date':'2027-09-06','weeks':20,'deadline':'2027-08-31T23:59:00'});r.raise_for_status();plan=r.json()
 print('Blank planner demo',plan['id'])
