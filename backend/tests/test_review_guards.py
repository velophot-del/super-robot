"""权限、调课输入与自动排课保存门槛回归。"""
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import test_debug_mode
from app.models.class_info import ClassInfo
from app.models.classroom import Classroom
from app.models.course import Course
from app.models.schedule import ScheduleEntry
from app.models.teacher import Teacher
from app.services.authorization import can


class SelfGrantTests(unittest.TestCase):
    def test_self_grant_requires_bound_identity_and_explicit_resource(self):
        user = SimpleNamespace(teacher_id=None, grants=[{'capability':'admin','scope':'self','scope_id':''}])
        self.assertFalse(can(user, 'admin'))
        user.teacher_id = 7
        self.assertFalse(can(user, 'admin'))
        self.assertTrue(can(user, 'admin', {'teacher_id':7}))
        self.assertFalse(can(user, 'admin', {'teacher_id':8}))
        user.grants[0]['scope'] = 'all'
        self.assertTrue(can(user, 'admin'))


class ScheduleGuardTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def prepare(self):
        self.db.add_all([
            ClassInfo(id=21,name='Audit class',grade='2026',department='Design',student_count=30),
            Classroom(id=31,name='Audit room',room_code='AUDIT-31',capacity=40),
            Course(id=11,name='Audit course',course_code='AUDIT-11',department='Design'),
            ScheduleEntry(id=701,schedule_version='schedule_100_old',teacher_id=7,course_id=11,
                          class_id=21,classroom_id=31,week_number=1,day_of_week=1,period_start=1,period_end=2),
        ])
        self.db.get(Teacher,7).department='Design'
        self.db.commit()
        response=await self.client.post('/api/debug/session',json={'role':'admin'})
        return {'Authorization':f"Bearer {response.json()['access_token']}"}

    async def test_manual_update_rejects_invalid_merged_periods_and_nulls(self):
        headers=await self.prepare()
        for payload in [{'period_start':8,'period_end':2},{'period_start':3},
                        {'period_end':None},{'teacher_id':None},{'status':None}]:
            with self.subTest(payload=payload):
                response=await self.client.put('/api/schedules/701',headers=headers,json=payload)
                self.assertEqual(response.status_code,422,response.text)
                self.db.expire_all()
                entry=self.db.get(ScheduleEntry,701)
                self.assertEqual((entry.period_start,entry.period_end,entry.teacher_id),(1,2,7))
        response=await self.client.put('/api/schedules/701',headers=headers,json={'period_start':3,'period_end':4})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['period_start'],3)

    async def test_manual_update_rejects_missing_teacher_or_room(self):
        headers=await self.prepare()
        for payload in [{'teacher_id':999},{'classroom_id':999}]:
            with self.subTest(payload=payload):
                response=await self.client.put('/api/schedules/701',headers=headers,json=payload)
                self.assertEqual(response.status_code,422,response.text)
                self.db.expire_all()
                entry=self.db.get(ScheduleEntry,701)
                self.assertEqual((entry.teacher_id,entry.classroom_id),(7,31))

    async def test_generate_blocks_engine_or_detector_hard_conflicts_without_writes(self):
        headers=await self.prepare()
        for engine_conflicts,capacity in [(1,40),(0,1),(0,40)]:
            self.db.get(Classroom,31).capacity=capacity
            self.db.commit()
            result={'success':True,'version':'schedule_200_new','hard_conflicts':engine_conflicts,
                    'soft_conflicts':0,'total_entries':1,'quality_score':90,
                    'entries':[{'course_id':11,'teacher_id':7,'class_id':21,'classroom_id':31,
                                'week_number':1,'day_of_week':1,'period_start':1,'period_end':2}]}
            with self.subTest(engine_conflicts=engine_conflicts,capacity=capacity):
                with patch('app.api.schedules.SchedulingEngine.run',return_value=result):
                    response=await self.client.post('/api/schedules/generate',headers=headers,json={})
                expected=200 if engine_conflicts==0 and capacity==40 else 409
                self.assertEqual(response.status_code,expected,response.text)
                self.assertEqual(self.db.query(ScheduleEntry).count(),2 if expected==200 else 1)
