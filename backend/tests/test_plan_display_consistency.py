from datetime import date, datetime
import unittest
import test_debug_mode
from app.models.planning import AcademicPlan, PublishedPlan, TeachingTask


class PlanDisplayConsistencyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_teacher_and_admin_read_same_published_snapshot_not_live_task(self):
        plan=AcademicPlan(name='Live renamed',start_date=date(2026,9,7),weeks=20,
            deadline=datetime(2026,9,1),state='published',revision=3,settings={})
        self.db.add(plan);self.db.flush()
        self.db.add(TeachingTask(plan_id=plan.id,payload={'name':'Changed live task','code':'C',
            'group':'G','start_week':8,'end_week':10}))
        info={'id':plan.id,'name':'Published cycle','start_date':'2026-09-07','weeks':20,
            'revision':2,'groups':['G'],'deadline':'2026-09-01T00:00:00Z'}
        task={'id':71,'name':'Published course','group':'G','start_week':1,'end_week':5,
            'teacher_ids':[7],'teacher_names':['Published teacher'],'room_name':'501','slots':[]}
        snapshot=PublishedPlan(plan_id=plan.id,payload={'plan':info,'tasks':[task]})
        self.db.add(snapshot);self.db.commit()
        results=[]
        for role in ('teacher','admin'):
            identity={'role':role,**({'teacher_id':7} if role=='teacher' else {})}
            token=(await self.client.post('/api/debug/session',json=identity)).json()['access_token']
            response=await self.client.get(f'/api/planning/plans/{plan.id}',headers={'Authorization':f'Bearer {token}'})
            self.assertEqual(response.status_code,200,response.text)
            data=response.json();results.append(data)
            self.assertEqual(data['snapshot_id'],snapshot.id)
            self.assertEqual(data['name'],'Published cycle')
            self.assertEqual(data['revision'],2)
            self.assertEqual(data['tasks'][0]['teacher_names'],['Published teacher'])
            self.assertEqual((data['tasks'][0]['start_week'],data['tasks'][0]['end_week']),(1,5))
        for data in results:
            self.assertEqual(data['tasks'][0]['id'],71)
        self.assertNotIn('applicants',self.db.get(PublishedPlan,snapshot.id).payload['tasks'][0])
