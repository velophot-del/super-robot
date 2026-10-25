import unittest
import test_debug_mode
import test_department_review
from app.models.planning import AcademicPlan, PreferenceSubmission, TeachingTask


class ReviewResourceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown
    headers = test_department_review.DepartmentReviewTests.headers
    plan = test_department_review.DepartmentReviewTests.plan
    task = test_department_review.DepartmentReviewTests.task
    prepare = test_department_review.DepartmentReviewTests.prepare

    async def test_director_can_load_review_options_without_management_permission(self):
        pid,task,sid,admin,_,director=await self.prepare()
        for path in ['/api/teachers/','/api/classrooms/']:
            self.assertEqual((await self.client.get(path,headers=director)).status_code,403)
        response=await self.client.get(f'/api/planning/plans/{pid}/tasks/{task}/review-options',headers=director)
        self.assertEqual(response.status_code,200,response.text)
        data=response.json()
        self.assertEqual([r['teacher_id'] for r in data['teachers']],[7])
        self.assertEqual(data['teachers'][0]['review_status'],'pending')
        self.assertEqual([r['id'] for r in data['rooms']],[31])
        self.assertNotIn('phone',response.text)
        self.assertNotIn('password',response.text)
        approved=await self.client.post(f'/api/planning/plans/{pid}/department-reviews',headers=admin,
            json={'submission_id':sid,'task_id':task,'approved':True,'reason':'Qualified'})
        self.assertEqual(approved.status_code,200,approved.text)
        current=await self.client.get(f'/api/planning/plans/{pid}/tasks/{task}/review-options',headers=director)
        self.assertEqual(current.json()['teachers'][0]['review_status'],'approved')
        self.assertTrue(current.json()['can_assign'])

    async def test_options_hide_other_departments_and_reject_unrelated_tasks(self):
        pid,task,_,admin,teacher,director=await self.prepare()
        plan=self.db.get(AcademicPlan,pid)
        other=TeachingTask(plan_id=pid,payload={**self.db.get(TeachingTask,task).payload,'group':'Private group'})
        self.db.add(other);self.db.flush()
        self.db.add(PreferenceSubmission(plan_id=pid,teacher_id=9,plan_revision=plan.revision,draft_revision=1,task_ids=[task,other.id]))
        self.db.commit()
        visible=await self.client.get(f'/api/planning/plans/{pid}/tasks/{task}/review-options',headers=director)
        self.assertEqual(visible.status_code,200,visible.text)
        self.assertEqual([r['teacher_id'] for r in visible.json()['teachers']],[7])
        for headers in [director,teacher]:
            denied=await self.client.get(f'/api/planning/plans/{pid}/tasks/{other.id}/review-options',headers=headers)
            self.assertEqual(denied.status_code,403,denied.text)
        all_rows=await self.client.get(f'/api/planning/plans/{pid}/tasks/{task}/review-options',headers=admin)
        self.assertEqual({r['teacher_id'] for r in all_rows.json()['teachers']},{7,8,9})

    async def test_options_require_login_and_validate_task_cycle(self):
        pid,task,_,admin,_,director=await self.prepare()
        url=f'/api/planning/plans/{pid}/tasks/{task}/review-options'
        self.assertEqual((await self.client.get(url)).status_code,401)
        missing=await self.client.get(f'/api/planning/plans/{pid}/tasks/99999/review-options',headers=admin)
        self.assertEqual(missing.status_code,404)
        plan=self.db.get(AcademicPlan,pid);plan.state='published';self.db.commit()
        self.assertEqual((await self.client.get(url,headers=director)).status_code,409)
