from copy import deepcopy
import unittest
import test_debug_mode
import test_planning_workflow
from app.models.planning import AcademicPlan, TeachingTask
from app.models.class_info import ClassInfo


class TaskLimitsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown
    headers=test_planning_workflow.PlanningWorkflowTests.headers
    plan=test_planning_workflow.PlanningWorkflowTests.plan
    task=test_planning_workflow.PlanningWorkflowTests.task

    async def create_task(self):
        pid=await self.plan();h=await self.headers()
        payload={**self.task(),'mode':'collaborative','tail_weeks':1,'slots':[],
                 'source':{'document_id':42,'revision':1,'course_metadata':{'name':'Typography','required_hours':8}}}
        response=await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=h,json=payload)
        self.assertEqual(response.status_code,200,response.text)
        return pid,h,response.json()

    async def test_limits_edit_preserves_imported_course_stage_mode_and_room_without_preset_students(self):
        pid,h,task=await self.create_task()
        original=deepcopy(self.db.get(TeachingTask,task['id']).payload)
        url=f"/api/planning/plans/{pid}/tasks/{task['id']}/limits"
        result=await self.client.put(url,headers=h,json={'revision':2,'teacher_count':2,'max_students':45})
        self.assertEqual(result.status_code,200,result.text)
        updated=deepcopy(self.db.get(TeachingTask,task['id']).payload)
        self.assertEqual(updated.pop('max_students'),45)
        updated.pop('teacher_count');original.pop('teacher_count');original.pop('max_students',None)
        self.assertEqual(updated,original)
        self.assertEqual(result.json()['task']['student_count'],0)
        self.assertEqual(result.json()['task']['actual_student_count'],0)
        self.assertEqual((await self.client.put(url,headers=h,json={'revision':2,'teacher_count':1,'max_students':40})).status_code,409)
        forged=await self.client.put(url,headers=h,json={'revision':3,'teacher_count':2,'max_students':45,'start_week':7})
        self.assertEqual(forged.status_code,422)
        denied=await self.client.put(url,headers=await self.headers('teacher'),json={'revision':3,'teacher_count':2,'max_students':45})
        self.assertEqual(denied.status_code,403)
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/open',headers=h)).status_code,200)
        self.assertEqual((await self.client.put(url,headers=h,json={'revision':3,'teacher_count':1,'max_students':40})).status_code,409)

    async def test_actual_students_are_entered_after_scheduling_not_taken_from_roster(self):
        pid,h,task=await self.create_task()
        self.assertEqual(task['student_count'],0)
        self.db.add(ClassInfo(name='Class A',grade='2026',student_count=40));self.db.commit()
        limits=f"/api/planning/plans/{pid}/tasks/{task['id']}/limits"
        # 班级人数不是选课人数；设置上限时不拿班级花名册阻断。
        valid=await self.client.put(limits,headers=h,json={'revision':2,'teacher_count':1,'max_students':35})
        self.assertEqual(valid.status_code,200,valid.text)
        actual=f"/api/planning/plans/{pid}/tasks/{task['id']}/actual-students"
        blocked=await self.client.put(actual,headers=h,json={'student_count':33})
        self.assertEqual(blocked.status_code,409,blocked.text)
        plan=self.db.get(AcademicPlan,pid)
        plan.state='matched';self.db.commit()
        too_many=await self.client.put(actual,headers=h,json={'student_count':40})
        self.assertEqual(too_many.status_code,409,too_many.text)
        saved=await self.client.put(actual,headers=h,json={'student_count':33})
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(saved.json()['student_count'],33)
        self.assertEqual(saved.json()['actual_student_count'],33)
