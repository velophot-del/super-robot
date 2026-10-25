import json
import unittest
from datetime import date, datetime
from unittest.mock import patch

import test_debug_mode
import test_department_review
from app.models.planning import (AcademicPlan, PeriodSlot, PreferenceSubmission, TeacherProfile,
                                 TeachingTask, PlanningEvent)
from app.models.teacher import Teacher
from app.services.ai_config import LLMError


class DepartmentAiReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown
    headers = test_department_review.DepartmentReviewTests.headers
    plan = test_department_review.DepartmentReviewTests.plan
    task = test_department_review.DepartmentReviewTests.task
    prepare = test_department_review.DepartmentReviewTests.prepare

    async def test_director_can_analyze_matching_without_approving_or_assigning(self):
        pid,task,_,_,teacher,director=await self.prepare()
        event_count=self.db.query(PlanningEvent).count()
        response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?use_ai=false',headers=director)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result['source'],'rules')
        self.assertEqual(result['stats']['teachers'],1)
        self.assertEqual(result['applications'][0]['professional_fit'],100)
        self.assertEqual(result['applications'][0]['review_status'],'pending')
        self.assertEqual(self.db.query(PlanningEvent).count(),event_count)
        forbidden=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?use_ai=false',headers=teacher)
        self.assertEqual(forbidden.status_code,403)
        cross_scope=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?unit_id=2&use_ai=false',headers=director)
        self.assertEqual(cross_scope.status_code,403)

    async def test_other_unit_details_and_self_application_are_excluded(self):
        pid,task,_,_,_,director=await self.prepare()
        self.db.get(Teacher,9).name='PRIVATE_OTHER_UNIT_NAME'
        self.db.get(Teacher,9).phone='PRIVATE_PHONE'
        plan=self.db.get(AcademicPlan,pid)
        for tid in [8,9]:
            self.db.add(PreferenceSubmission(plan_id=pid,teacher_id=tid,plan_revision=plan.revision,draft_revision=1,task_ids=[task]))
        self.db.commit()
        response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?use_ai=false',headers=director)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual({r['teacher_id'] for r in response.json()['applications']},{7})
        self.assertNotIn('PRIVATE_',response.text)
        self.assertIn('其他教研室1人',response.text)

    async def test_cross_cycle_selected_teacher_conflicts_and_low_fit_are_found(self):
        pid,task,_,_,_,director=await self.prepare()
        other_plan=AcademicPlan(name='Another cycle',start_date=date(2027,2,1),deadline=datetime(2027,4,1),
                                state='open',revision=1,settings={'term':2})
        self.db.add(other_plan);self.db.flush()
        data={**self.db.get(TeachingTask,task).payload,'name':'Other course','code':'B','group':'Other class',
              'direction':'Other direction','tags':['other']}
        other=TeachingTask(plan_id=other_plan.id,payload=data);self.db.add(other);self.db.flush()
        self.db.add(PeriodSlot(task_id=other.id,day=1,start=1,count=4))
        self.db.add(PreferenceSubmission(plan_id=other_plan.id,teacher_id=7,plan_revision=1,draft_revision=1,task_ids=[other.id]))
        self.db.commit()
        response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?use_ai=false',headers=director)
        self.assertEqual(response.status_code,200,response.text)
        rows=response.json()['applications']
        self.assertEqual(len(rows),2)
        self.assertTrue(any(i['category']=='teacher_time' for row in rows for i in row['issues']))
        low=next(row for row in rows if row['task_id']==other.id)
        self.assertEqual(low['professional_fit'],0)
        self.assertTrue(any(i['category']=='low_fit' for i in low['issues']))

    async def test_missing_profiles_or_slots_are_unknown_not_fabricated_scores(self):
        pid,task,_,_,_,director=await self.prepare()
        row=self.db.get(TeachingTask,task);row.payload={**row.payload,'direction':'','tags':[],'room_id':None}
        self.db.query(PeriodSlot).filter_by(task_id=task).delete();self.db.commit()
        response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?use_ai=false',headers=director)
        result=response.json()['applications'][0]
        self.assertIsNone(result['professional_fit'])
        categories={i['category'] for i in result['issues']}
        self.assertTrue({'missing_profile','missing_slots','missing_room'}<=categories)
        self.assertNotIn('teacher_time',categories)

    async def test_llm_receives_only_scoped_pseudonymous_evidence(self):
        pid,_,_,_,_,director=await self.prepare()
        self.db.get(Teacher,7).phone='PRIVATE_PHONE'
        self.db.get(Teacher,7).email='private@example.invalid'
        profile=self.db.get(TeacherProfile,7)
        profile.payload={**profile.payload,'self_profile':{**profile.payload['self_profile'],'bio':'PRIVATE_BIO'}}
        self.db.commit()

        def model_call(config,system,payload,**kwargs):
            self.assertFalse(self.db.in_transaction())
            self.assertNotIn('Demo teacher',payload)
            self.assertNotIn('PRIVATE_',payload)
            self.assertNotIn('private@example.invalid',payload)
            self.assertNotIn('TEST-7',payload)
            self.assertEqual(json.loads(payload)['applications'][0]['teacher'],'T1')
            return {'text':'T1：专业匹配充分，仍应核实课程竞争。','model':'mock-model'}

        with patch('app.services.department_ai_review.resolve_config',return_value={'api_key':'test-key','provider':'test'}), \
             patch('app.services.department_ai_review.call_llm',side_effect=model_call):
            response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review',headers=director)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['source'],'llm')
        self.assertEqual(response.json()['teacher_aliases'],[{'alias':'T1','teacher_name':'Demo teacher'}])

    async def test_model_failure_falls_back_without_leaking_error_details(self):
        pid,_,_,_,_,director=await self.prepare()
        with patch('app.services.department_ai_review.resolve_config',return_value={'api_key':'test-key'}), \
             patch('app.services.department_ai_review.call_llm',side_effect=LLMError('PRIVATE_KEY')):
            response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review',headers=director)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['source'],'rules')
        self.assertNotIn('PRIVATE_KEY',response.text)

    async def test_model_result_is_rejected_if_profile_changes_during_analysis(self):
        pid,_,_,_,_,director=await self.prepare()

        def changed(*args,**kwargs):
            profile=self.db.get(TeacherProfile,7);profile.revision+=1;self.db.commit()
            return {'text':'Old result','model':'mock'}

        with patch('app.services.department_ai_review.resolve_config',return_value={'api_key':'test-key'}), \
             patch('app.services.department_ai_review.call_llm',side_effect=changed):
            response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review',headers=director)
        self.assertEqual(response.status_code,409,response.text)
        self.assertNotIn('Old result',response.text)

    async def test_absent_configuration_and_empty_scope_do_not_call_model(self):
        pid,_,_,admin,_,director=await self.prepare()
        with patch('app.services.department_ai_review.resolve_config',return_value=None), \
             patch('app.services.department_ai_review.call_llm') as model:
            response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review',headers=director)
            self.assertEqual(response.json()['source'],'rules')
            self.assertIn('未配置',response.json()['reason'])
            empty=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?unit_id=2',headers=admin)
            self.assertEqual(empty.json()['stats']['teachers'],0)
            model.assert_not_called()

    async def test_external_room_conflicts_are_anonymous(self):
        pid,task,_,_,_,director=await self.prepare()
        other_plan=AcademicPlan(name='PRIVATE_PLAN',start_date=date(2027,2,1),deadline=datetime(2027,4,1),
                                state='matched',revision=1,settings={'term':2})
        self.db.add(other_plan);self.db.flush()
        other=TeachingTask(plan_id=other_plan.id,payload={**self.db.get(TeachingTask,task).payload,
            'name':'PRIVATE_COURSE','group':'PRIVATE_CLASS'})
        self.db.add(other);self.db.flush()
        self.db.add(PeriodSlot(task_id=other.id,day=1,start=1,count=4));self.db.commit()
        response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?use_ai=false',headers=director)
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(any(i['category']=='room_conflict' for row in response.json()['applications'] for i in row['issues']))
        self.assertNotIn('PRIVATE_',response.text)

    async def test_course_limit_is_checked_without_slots_but_time_overlap_remains_risk(self):
        pid,task,_,_,_,director=await self.prepare()
        tasks=[task]
        for index in range(3):
            other=TeachingTask(plan_id=pid,payload={**self.db.get(TeachingTask,task).payload,
                'code':f'OTHER{index}','name':f'Course {index}','group':f'Class {index}'})
            self.db.add(other);self.db.flush();tasks.append(other.id)
        self.db.query(PeriodSlot).filter_by(task_id=task).delete()
        self.db.add(PreferenceSubmission(plan_id=pid,teacher_id=7,plan_revision=self.db.get(AcademicPlan,pid).revision,
                                        draft_revision=2,task_ids=tasks));self.db.commit()
        response=await self.client.post(f'/api/planning/plans/{pid}/department-ai-review?use_ai=false',headers=director)
        self.assertEqual(response.status_code,200,response.text)
        issues=[i for row in response.json()['applications'] for i in row['issues']]
        self.assertTrue(any(i['category']=='teacher_capacity' and '课程数4' in i['message'] for i in issues))
        self.assertTrue(any(i['category']=='span_overlap' and i['level']=='warning' for i in issues))
        self.assertFalse(any(i['category']=='teacher_time' for i in issues))
