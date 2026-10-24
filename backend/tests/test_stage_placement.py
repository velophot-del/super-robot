import unittest
import test_debug_mode
from datetime import date,datetime
from app.models.planning import AcademicPlan
from app.models.class_info import ClassInfo
from app.models.course import Course


class StagePlacementTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_identical_import_rows_share_one_course_but_distinct_hours_remain(self):
        from app.services.course_catalog import courses_for_group
        group = ClassInfo(name='A', grade='2026', department='Design', student_count=30)
        self.db.add(group)
        for code, hours in [('A', 54), ('B', 54), ('C', 72)]:
            self.db.add(Course(name='UI', course_code=code, semester=4, cohort='2026',
                               department='Design', total_hours=hours, teaching_weeks=4))
        self.db.commit()
        rows = courses_for_group(self.db, group, 4)
        self.assertEqual([row.course_code for row in rows], ['A', 'C'])

    async def test_pool_merges_cohort_aliases_and_keeps_all_classes(self):
        from app.services.course_catalog import course_pool_rows
        course = Course(id=1, name='Intro', course_code='A', total_hours=8, teaching_weeks=1)
        groups = [ClassInfo(name=name, grade=grade, department='Design', student_count=30)
                  for name, grade in [('A', '2026'), ('B', '2026届'), ('C', '2026级')]]
        rows = course_pool_rows([{'class': g, 'semester': 1, 'courses': [course]} for g in groups])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['cohort'], '2026')
        self.assertEqual(rows[0]['groups'], ['A', 'B', 'C'])

    async def test_exam_week_scope_normalizes_cohort_labels_across_majors(self):
        from app.services.exam_weeks import exam_weeks_for, normalize_exam_weeks
        settings={'weeks':20,'exam_weeks':{'2024':[6],'2024届':[5]}}
        self.assertEqual(normalize_exam_weeks(settings['exam_weeks'],20),{'2024':[5,6]})
        self.assertEqual(exam_weeks_for(settings,'2024级','视觉班',20),{5,6})
        self.assertEqual(exam_weeks_for(settings,'2024','包装班',20),{5,6})

    async def test_drop_persists_span_moves_and_rejects_exam_overflow_or_stale(self):
        h={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        self.db.add_all([ClassInfo(name=name,grade='2026',department='Design',student_count=30) for name in ('A','B')])
        self.db.add(Course(name='Typography',course_code='A',credits=4,total_hours=72,semester=1,cohort='2026',
            department='Design',teaching_weeks=5,tail_hours=8))
        self.db.add(AcademicPlan(id=1,name='Term',start_date=date(2027,9,6),weeks=20,deadline=datetime(2027,8,1),state='draft',revision=1,settings={'major':'Design','cohort':'2026','semester':1,'groups':['A','B']}));self.db.commit()
        r=await self.client.get('/api/planning/plans/1/course-pool',headers=h);self.assertEqual(r.status_code,200,r.text);course=r.json()['courses'][0]
        data={'revision':1,'course_id':course['id'],'group':'A','start_week':2}
        r=await self.client.put('/api/planning/plans/1/placement',headers=h,json=data);self.assertEqual(r.status_code,200,r.text)
        task=r.json()['task'];self.assertEqual((task['start_week'],task['end_week']),(2,6));self.assertEqual(task['tail_weeks'],1)
        self.assertEqual(task['slots'],[])
        self.assertEqual((await self.client.put('/api/planning/plans/1/placement',headers=h,json=data)).status_code,409)
        move={'revision':2,'task_id':task['id'],'group':'B','start_week':7}
        r=await self.client.put('/api/planning/plans/1/placement',headers=h,json=move);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['task']['end_week'],11)
        move.update(revision=3,start_week=15)
        r=await self.client.put('/api/planning/plans/1/placement',headers=h,json=move);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['task']['end_week'],19)
        move.update(revision=4,start_week=16)
        self.assertEqual((await self.client.put('/api/planning/plans/1/placement',headers=h,json=move)).status_code,409)
        self.assertEqual((await self.client.post('/api/planning/plans/1/open',headers=h)).status_code,200)

    async def test_placement_uses_course_plan_weeks_and_ignores_client_duration(self):
        h = {'Authorization': 'Bearer ' + (await self.client.post(
            '/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        self.db.add(ClassInfo(name='A', grade='2026', department='Design', student_count=30))
        self.db.add(Course(name='Typography', course_code='A', credits=4, total_hours=64,
                           semester=1, cohort='2026', department='Design', teaching_weeks=5,
                           weekdays=[1, 3]))
        self.db.add(AcademicPlan(id=1, name='Term', start_date=date(2027, 9, 6), weeks=20,
                                 deadline=datetime(2027, 8, 1), state='draft', revision=1,
                                 settings={'major': 'Design', 'cohort': '2026', 'semester': 1,
                                           'groups': ['A']}))
        self.db.commit()
        pool = (await self.client.get('/api/planning/plans/1/course-pool', headers=h)).json()
        course = pool['courses'][0]
        self.assertEqual(course['teaching_weeks'], 5)
        placed = await self.client.put('/api/planning/plans/1/placement', headers=h, json={
            'revision': 1, 'course_id': course['id'], 'group': 'A',
            'start_week': 2, 'duration': 2})
        self.assertEqual(placed.status_code, 200, placed.text)
        task = placed.json()['task']
        self.assertEqual((task['start_week'], task['end_week']), (2, 6))

    async def test_missing_plan_weeks_are_derived_from_sessions(self):
        h = {'Authorization': 'Bearer ' + (await self.client.post(
            '/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        self.db.add(ClassInfo(name='A', grade='2026', department='Design', student_count=30))
        self.db.add(Course(name='Typography', course_code='A', credits=4, total_hours=32,
                           semester=1, cohort='2026', department='Design', teaching_weeks=None,
                           weekdays=[1, 3]))
        self.db.add(AcademicPlan(id=1, name='Term', start_date=date(2027, 9, 6), weeks=20,
                                 deadline=datetime(2027, 8, 1), state='draft', revision=1,
                                 settings={'major': 'Design', 'cohort': '2026', 'semester': 1,
                                           'groups': ['A']}))
        self.db.commit()
        pool = (await self.client.get('/api/planning/plans/1/course-pool', headers=h)).json()
        course = pool['courses'][0]
        self.assertEqual(course['teaching_weeks'], 8)
        placed = await self.client.put('/api/planning/plans/1/placement', headers=h, json={
            'revision': 1, 'course_id': course['id'], 'group': 'A', 'start_week': 2})
        self.assertEqual(placed.status_code, 200, placed.text)
        self.assertEqual(placed.json()['task']['end_week'], 9)

    async def test_groups_can_be_added_in_draft_and_open_but_not_published(self):
        h={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        self.db.add(AcademicPlan(id=90,name='Groups',start_date=date(2027,9,6),weeks=20,
                                 deadline=datetime(2027,8,1),state='draft',revision=1,
                                 settings={'groups':['A']}))
        self.db.commit()
        url='/api/planning/plans/90/groups'
        added=await self.client.put(url,headers=h,json={'revision':1,'groups':['A','B']})
        self.assertEqual(added.status_code,200,added.text)
        self.assertEqual(added.json()['revision'],2)
        plan=self.db.get(AcademicPlan,90);self.assertEqual(plan.settings['groups'],['A','B'])
        plan.state='open';self.db.commit()
        # 开放阶段增加班级不递增版本，避免已提交志愿失效。
        opened=await self.client.put(url,headers=h,json={'revision':2,'groups':['A','B','C']})
        self.assertEqual(opened.status_code,200,opened.text)
        self.assertEqual(opened.json()['revision'],2)
        plan=self.db.get(AcademicPlan,90);self.assertEqual(plan.settings['groups'],['A','B','C'])
        plan.state='published';self.db.commit()
        frozen=await self.client.put(url,headers=h,json={'revision':2,'groups':['A']})
        self.assertEqual(frozen.status_code,409,frozen.text)

    async def test_moving_manual_course_preserves_tail_periods(self):
        from app.models.planning import TeachingTask,PeriodSlot
        h={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        self.db.add(AcademicPlan(id=1,name='Term',start_date=date(2027,9,6),weeks=20,deadline=datetime(2027,8,1),state='draft',revision=1,settings={'groups':['G']}));self.db.flush()
        self.db.add(TeachingTask(id=1,plan_id=1,payload={'name':'Manual','code':'M','group':'G','start_week':1,'end_week':3,'tail_weeks':1,'required_hours':10,'credits':1}));self.db.flush()
        self.db.add_all([PeriodSlot(task_id=1,day=1,start=1,count=4,phase='normal'),PeriodSlot(task_id=1,day=1,start=1,count=2,phase='tail')]);self.db.commit()
        r=await self.client.put('/api/planning/plans/1/placement',headers=h,json={'revision':1,'task_id':1,'group':'G','start_week':5})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['task']['tail_weeks'],1)

    async def test_ai_autofill_places_catalog_courses_in_draft_and_preserves_manual_spans(self):
        from app.models.planning import TeachingTask
        h={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        self.db.add(ClassInfo(name='G',grade='2026',department='视觉传达设计',student_count=30))
        self.db.add_all([
            Course(name='版式设计',course_code='C1',credits=4,total_hours=48,semester=1,cohort='2026',
                department='视觉传达设计',teaching_weeks=3),
            Course(name='文字设计',course_code='C2',credits=4,total_hours=48,semester=1,cohort='2026',
                department='视觉传达设计',teaching_weeks=3),
        ])
        plan=AcademicPlan(id=71,name='AI空表填充',start_date=date(2026,9,6),weeks=8,
            deadline=datetime(2027,8,1),state='draft',revision=1,
            settings={'groups':['G'],'semester':1,'major':'视觉传达设计','cohort':'2026','exam_weeks':{'2026':[4],'*':[]}})
        self.db.add(plan);self.db.flush()
        self.db.add(TeachingTask(id=710,plan_id=71,payload={'name':'人工安排','code':'M','group':'G','class_name':'G',
            'start_week':1,'end_week':2,'tail_weeks':0,'required_hours':32,'slots':[],'source':{},'cohort':'2026'}))
        self.db.commit()
        response=await self.client.post('/api/planning/plans/71/auto-fill/ai',headers=h,json={'revision':1})
        self.assertEqual(response.status_code,200,response.text)
        body=response.json()
        self.assertEqual(body['filled'],2)
        self.assertEqual(body['source'],'rules')
        tasks=self.db.query(TeachingTask).filter_by(plan_id=71).all()
        self.assertEqual(len(tasks),3)
        self.assertEqual(self.db.get(TeachingTask,710).payload['start_week'],1)
        generated=[task.payload for task in tasks if task.id!=710]
        self.assertEqual({task['start_week'] for task in generated},{1,5})
        self.assertTrue(all(task['end_week']<4 or task['start_week']>4 for task in generated))
        self.assertTrue(all(not task.get('slots') for task in generated))

    async def test_ai_autofill_reports_courses_without_weeks(self):
        h={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        self.db.add(ClassInfo(name='G',grade='2026',department='Design',student_count=30))
        self.db.add(Course(name='Too long',course_code='NW',credits=2,total_hours=500,semester=1,cohort='2026',department='Design',teaching_weeks=9))
        self.db.add(AcademicPlan(id=72,name='AI missing metadata',start_date=date(2026,9,6),weeks=8,
            deadline=datetime(2027,8,1),state='draft',revision=1,settings={'groups':['G'],'semester':1,'major':'Design','cohort':'2026'}));self.db.commit()
        response=await self.client.post('/api/planning/plans/72/auto-fill/ai',headers=h,json={'revision':1})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['filled'],0)
        self.assertIn('周段不足',response.json()['unplaced'][0]['reason'])
