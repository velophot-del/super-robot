import unittest
from types import SimpleNamespace
from datetime import date, datetime, timedelta
from fastapi import HTTPException
import test_debug_mode
import test_planning_workflow
from app.models.teacher import Teacher
from app.models.planning import (AcademicPlan, PreferenceSubmission, TeachingTask, OfferingUnit)
from app.services import department_review


class DepartmentReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown
    headers = test_planning_workflow.PlanningWorkflowTests.headers
    plan = test_planning_workflow.PlanningWorkflowTests.plan
    task = test_planning_workflow.PlanningWorkflowTests.task

    async def prepare(self):
        pid=await self.plan();admin=await self.headers();teacher=await self.headers('teacher')
        self.db.add_all([OfferingUnit(id=1,code='U1',name='Unit 1'),OfferingUnit(id=2,code='U2',name='Unit 2')])
        self.db.flush()
        self.db.get(Teacher,7).offering_unit_id=1
        self.db.add(Teacher(id=8,name='Director',teacher_code='T8',offering_unit_id=1,
                            position='教研室主任',review_major='Design'))
        self.db.add(Teacher(id=9,name='Other teacher',teacher_code='T9',offering_unit_id=2))
        self.db.commit()
        task=(await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=admin,json=self.task())).json()
        self.assertIn('id',task)
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/enable-department-review',headers=admin)).status_code,200)
        await self.client.post(f'/api/planning/plans/{pid}/open',headers=admin)
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=teacher)).json()
        draft=(await self.client.put(f'/api/planning/plans/{pid}/draft',headers=teacher,
            json={'revision':0,'plan_revision':state['revision'],'task_ids':[task['id']]})).json()
        submission=(await self.client.post(f'/api/planning/plans/{pid}/submit',headers=teacher,json={'revision':draft['revision']})).json()
        login=await self.client.post('/api/debug/session',json={'role':'teacher','teacher_id':8})
        director={'Authorization':'Bearer '+login.json()['access_token']}
        return pid,task['id'],submission['id'],admin,teacher,director

    async def test_initial_review_gates_matching_and_room_change_preserves_approval(self):
        pid,task,sid,admin,_,director=await self.prepare()
        blocked=await self.client.post(f'/api/planning/plans/{pid}/match',headers=admin)
        self.assertEqual(blocked.status_code,409,blocked.text)
        approved=await self.client.post(f'/api/planning/plans/{pid}/department-reviews',headers=director,
            json={'submission_id':sid,'task_id':task,'approved':True,'reason':'Qualified'})
        self.assertEqual(approved.status_code,200,approved.text)
        room=await self.client.put(f'/api/planning/plans/{pid}/tasks/{task}/room',headers=director,json={'room_id':None})
        self.assertEqual(room.status_code,200,room.text)
        self.assertEqual(department_review.status(self.db,self.db.get(AcademicPlan,pid),self.db.get(PreferenceSubmission,sid),task),'approved')
        matched=await self.client.post(f'/api/planning/plans/{pid}/match',headers=admin)
        self.assertEqual(matched.status_code,200,matched.text)
        denied=await self.client.put(f'/api/planning/plans/{pid}/tasks/{task}/assignment',headers=director,
            json={'teacher_ids':[7],'match_id':matched.json()['id'],'reason':'Change'})
        self.assertEqual(denied.status_code,403,denied.text)

    async def test_director_scope_privacy_and_self_recusal(self):
        pid,task,sid,admin,teacher,director=await self.prepare()
        other=PreferenceSubmission(plan_id=pid,teacher_id=9,plan_revision=self.db.get(AcademicPlan,pid).revision,draft_revision=1,task_ids=[task])
        self.db.add(other);self.db.commit()
        visible=await self.client.get(f'/api/planning/plans/{pid}/department-reviews',headers=director)
        self.assertEqual([r['teacher_id'] for r in visible.json()],[7])
        denied=await self.client.post(f'/api/planning/plans/{pid}/department-reviews',headers=director,
            json={'submission_id':other.id,'task_id':task,'approved':True,'reason':'Wrong scope'})
        self.assertEqual(denied.status_code,403)
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=director,params={'review_only':True})).json()
        self.assertEqual([r['teacher_id'] for r in state['tasks'][0]['applicants']],[7])
        self.assertEqual(state['tasks'][0]['other_applicant_count'],1)
        # Administrator authority never permits self-approval.
        actor=SimpleNamespace(teacher_id=7,grants=[{'capability':'admin','scope':'all'}])
        self.assertFalse(department_review.may_review(self.db,actor,self.db.get(Teacher,7)))

    async def test_return_and_resubmission_do_not_reuse_old_approval(self):
        pid,task,sid,admin,teacher,director=await self.prepare()
        for approved in [True,False]:
            response=await self.client.post(f'/api/planning/plans/{pid}/department-reviews',headers=director,
                json={'submission_id':sid,'task_id':task,'approved':approved,'reason':'Please revise'})
            self.assertEqual(response.status_code,200,response.text)
        plan=self.db.get(AcademicPlan,pid);plan.state='matched';plan.deadline=datetime.utcnow()-timedelta(days=1);self.db.commit()
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=teacher)).json()
        self.assertTrue(state['can_resubmit'])
        saved=await self.client.put(f'/api/planning/plans/{pid}/draft',headers=teacher,
            json={'revision':state['draft']['revision'],'plan_revision':state['revision'],'task_ids':[task]})
        self.assertEqual(saved.status_code,200,saved.text)
        submitted=await self.client.post(f'/api/planning/plans/{pid}/submit',headers=teacher,json={'revision':saved.json()['revision']})
        self.assertEqual(submitted.status_code,200,submitted.text)
        self.assertNotEqual(submitted.json()['id'],sid)
        self.assertEqual(department_review.status(self.db,plan,self.db.get(PreferenceSubmission,submitted.json()['id']),task),'pending')
        stale=await self.client.post(f'/api/planning/plans/{pid}/department-reviews',headers=director,
            json={'submission_id':sid,'task_id':task,'approved':True,'reason':'Stale'})
        self.assertEqual(stale.status_code,409)

    async def test_rule_confirmation_and_overview_preserve_cycle_sources(self):
        pid,task,_,admin,_,director=await self.prepare()
        plan=self.db.get(AcademicPlan,pid);plan.rule_confirmed=False;self.db.commit()
        confirmed=await self.client.post(f'/api/planning/plans/{pid}/confirm-match-rules',headers=admin)
        self.assertEqual(confirmed.status_code,200)
        denied=await self.client.post(f'/api/planning/plans/{pid}/confirm-match-rules',headers=director)
        self.assertEqual(denied.status_code,403)
        second=AcademicPlan(name='Second cycle',start_date=date(2027,3,1),deadline=datetime(2027,4,1),state='open',settings={'term':2})
        self.db.add(second);self.db.commit()
        overview=await self.client.get('/api/planning/review-overview',headers=admin,params={'plan_id':pid})
        self.assertEqual(overview.status_code,200,overview.text)
        self.assertEqual({p['id'] for p in overview.json()['plans']},{pid,second.id})
        self.assertEqual(overview.json()['reviews'][0]['plan_id'],pid)

    async def test_room_check_includes_other_unpublished_cycle(self):
        from app.api.planning import validate_global_room
        from app.services.stage_planning import task_dict
        from app.models.planning import PeriodSlot
        pid,task,_,_,_,_=await self.prepare()
        second=AcademicPlan(name='Second',start_date=date(2027,2,1),deadline=datetime(2027,4,1),state='matched',settings={})
        self.db.add(second);self.db.flush()
        other=TeachingTask(plan_id=second.id,payload={**self.db.get(TeachingTask,task).payload,'group':'Other'})
        self.db.add(other);self.db.flush()
        self.db.add(PeriodSlot(task_id=other.id,day=1,start=1,count=4));self.db.commit()
        with self.assertRaises(HTTPException):
            validate_global_room(self.db,self.db.get(AcademicPlan,pid),task_dict(self.db,self.db.get(TeachingTask,task)),31)

    async def test_department_recommendation_does_not_reserve_course(self):
        from app.models.planning import TeachingAssignment
        pid,task,sid,admin,_,director=await self.prepare()
        url=f'/api/planning/plans/{pid}/tasks/{task}/department-recommendation'
        payload={'teacher_ids':[7],'reason':'Qualified department recommendation'}
        blocked=await self.client.put(url,headers=director,json=payload)
        self.assertEqual(blocked.status_code,409,blocked.text)
        await self.client.post(f'/api/planning/plans/{pid}/department-reviews',headers=director,
            json={'submission_id':sid,'task_id':task,'approved':True,'reason':'Qualified'})
        recommended=await self.client.put(url,headers=director,json=payload)
        self.assertEqual(recommended.status_code,200,recommended.text)
        self.assertIsNone(self.db.get(TeachingAssignment,task))
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=admin)).json()
        self.assertEqual(state['tasks'][0]['department_recommendations'][0]['teacher_names'],['Demo teacher'])

    async def test_enable_existing_assignment_releases_lock_without_deleting_submission(self):
        from app.models.planning import TeachingAssignment
        pid,task,sid,admin,_,_=await self.prepare()
        plan=self.db.get(AcademicPlan,pid);plan.settings={**plan.settings,'department_review':False};self.db.commit()
        matched=await self.client.post(f'/api/planning/plans/{pid}/match',headers=admin)
        self.assertEqual(matched.status_code,200,matched.text)
        self.assertTrue(self.db.get(TeachingAssignment,task).locked)
        enabled=await self.client.post(f'/api/planning/plans/{pid}/enable-department-review',headers=admin)
        self.assertEqual(enabled.status_code,200,enabled.text)
        self.db.expire_all()
        self.assertFalse(self.db.get(TeachingAssignment,task).locked)
        self.assertEqual(self.db.get(PreferenceSubmission,sid).task_ids,[task])

    async def test_global_student_week_limit_and_teacher_reservations_include_matched_plans(self):
        from app.api.planning import validate_global_student_scope, assigned_tasks
        from app.services.stage_planning import task_dict
        from app.models.planning import TeachingAssignment, MatchRun
        pid,task,_,_,_,_=await self.prepare()
        second=AcademicPlan(name='Other cycle',start_date=date(2027,2,1),deadline=datetime(2027,4,1),state='matched',settings={})
        self.db.add(second);self.db.flush()
        run=MatchRun(plan_id=second.id,payload={});self.db.add(run);self.db.flush()
        for index in range(2):
            other=TeachingTask(plan_id=second.id,payload={**self.db.get(TeachingTask,task).payload,'code':f'OTHER{index}'})
            self.db.add(other);self.db.flush()
            self.db.add(TeachingAssignment(task_id=other.id,teacher_ids=[7],match_id=run.id,locked=True))
        self.db.commit()
        self.assertEqual(len(assigned_tasks(self.db,self.db.get(AcademicPlan,pid),7)),2)
        with self.assertRaises(HTTPException):
            validate_global_student_scope(self.db,self.db.get(AcademicPlan,pid),task_dict(self.db,self.db.get(TeachingTask,task)))
