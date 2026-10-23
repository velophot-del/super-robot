from pathlib import Path
import tempfile
import unittest
from sqlalchemy import create_engine, text
import test_debug_mode
from app.database import _migrate_course_columns
from app.models.course import Course
from app.models.planning import TeacherProfile


class CourseGroupsLeadersTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def headers(self, role='admin'):
        payload = {'role': role}
        if role == 'teacher': payload['teacher_id'] = 7
        r = await self.client.post('/api/debug/session', json=payload)
        return {'Authorization': 'Bearer ' + r.json()['access_token']}

    async def test_groups_include_all_professional_courses_and_preserve_admin_provenance(self):
        self.db.add_all([Course(id=11, name='Design', course_code='D1', course_type='专业必修'),
                         Course(id=12, name='Design', course_code='D2', course_type='专业选修'),
                         Course(id=13, name='General', course_code='G1', course_type='公共课'),
                         Course(id=14, name='Civic education', course_code='G2', course_type='思政选修课')])
        self.db.add(TeacherProfile(teacher_id=7, revision=1, payload={'team_codes':['VERIFIED'], 'verified':True}))
        self.db.commit()
        headers = await self.headers('teacher')
        options = await self.client.get('/api/planning/self-profile/course-groups', headers=headers)
        self.assertEqual(options.status_code, 200, options.text)
        self.assertEqual({r['id'] for r in options.json()}, {11,12})
        data = {'revision':1,'direction':'Design','tags':['type'],'skilled_courses':['Design'],
                'participating_course_ids':[11,12,11]}
        saved = await self.client.put('/api/planning/self-profile', headers=headers, json=data)
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(saved.json()['profile']['participating_course_ids'],[11,12])
        profile=self.db.get(TeacherProfile,7)
        self.assertEqual(profile.payload['team_codes'],['VERIFIED'])
        admin=await self.headers()
        await self.client.put('/api/planning/profiles/7',headers=admin,json={'direction':'Admin','tags':['admin'],'verified':True})
        own=(await self.client.get('/api/planning/self-profile',headers=headers)).json()
        self.assertEqual(own['profile']['participating_course_ids'],[11,12])
        legacy_data={key:value for key,value in data.items() if key!='participating_course_ids'}
        legacy_data['revision']=own['revision']
        legacy=await self.client.put('/api/planning/self-profile',headers=headers,json=legacy_data)
        self.assertEqual(legacy.status_code,200,legacy.text)
        self.assertEqual(legacy.json()['profile']['participating_course_ids'],[11,12])
        own=legacy.json()
        for ids in [[9999],[13]]:
            bad=await self.client.put('/api/planning/self-profile',headers=headers,json={**data,'revision':own['revision'],'participating_course_ids':ids})
            self.assertEqual(bad.status_code,422,bad.text)

    async def test_leader_create_change_clear_invalid_and_teacher_denied(self):
        h=await self.headers()
        created=await self.client.post('/api/courses/',headers=h,json={'name':'Course','course_code':'C1','semester':2,'leader_teacher_id':7})
        self.assertEqual(created.status_code,201,created.text)
        row=created.json();self.assertEqual(row['leader_teacher_id'],7)
        self.assertEqual(row['leader_teacher_name'],'Demo teacher')
        self.assertEqual(row['leader_teacher_code'],'TEST-7')
        url=f"/api/courses/{row['id']}"
        renamed=await self.client.put(url,headers=h,json={'name':'Renamed'})
        self.assertEqual(renamed.json()['leader_teacher_id'],7)
        self.assertEqual(renamed.json()['leader_teacher_name'],'Demo teacher')
        invalid=await self.client.put(url,headers=h,json={'leader_teacher_id':9999})
        self.assertEqual(invalid.status_code,422,invalid.text)
        forbidden=await self.client.put(url,headers=await self.headers('teacher'),json={'leader_teacher_id':None})
        self.assertEqual(forbidden.status_code,403)
        self.assertEqual((await self.client.get(url,headers=h)).json()['leader_teacher_id'],7)
        cleared=await self.client.put(url,headers=h,json={'leader_teacher_id':None})
        self.assertEqual(cleared.status_code,200,cleared.text)
        self.assertIsNone(cleared.json()['leader_teacher_id'])
        self.assertIsNone(cleared.json()['leader_teacher_name'])

    async def test_teacher_management_reads_self_profile_groups_and_leader_courses(self):
        self.db.add_all([
            Course(id=21, name='Design A', course_code='DA', course_type='专业必修', leader_teacher_id=7),
            Course(id=22, name='Public', course_code='PB', course_type='公共课', leader_teacher_id=7),
            Course(id=23, name='Design B', course_code='DB', course_type='专业选修'),
        ])
        self.db.add(TeacherProfile(teacher_id=7, revision=1, payload={'self_profile': {
            'direction': 'Design', 'tags': ['type'], 'skilled_courses': ['Design'],
            'participating_course_ids': [21, 23]}}))
        self.db.commit()
        h = await self.headers()
        result = await self.client.get('/api/teachers/7/course-affiliations', headers=h)
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertTrue(data['profile_updated'])
        self.assertEqual([course['id'] for course in data['course_groups']], [21, 23])
        # 课程负责人只展示专业课程，公共课负责人不列入。
        self.assertEqual([course['id'] for course in data['leader_courses']], [21])

    async def test_csv_template_import_legacy_unknown_and_duplicates(self):
        h=await self.headers()
        template=await self.client.get('/api/io/template/courses',headers=h)
        self.assertIn('课程负责人（工号）',template.content.decode('utf-8-sig'))
        async def upload(content):
            return await self.client.post('/api/io/csv/courses',headers=h,files={'file':('courses.csv',content.encode(),'text/csv')})
        imported=await upload('课程名称,课程编码,上课学期,学期教学次数,课程负责人（工号）\nDesign,D1,2,16,TEST-7\n')
        self.assertEqual(imported.status_code,200,imported.text)
        self.assertTrue(imported.json()['success'],imported.text)
        self.assertEqual(self.db.query(Course).filter_by(course_code='D1').one().leader_teacher_id,7)
        repeat=await upload('课程名称,课程编码,上课学期,学期教学次数,课程负责人（工号）\nChanged,D1,2,16,UNKNOWN\n')
        self.assertEqual(repeat.json()['skipped'],1,repeat.text)
        self.assertEqual(self.db.query(Course).filter_by(course_code='D1').one().leader_teacher_id,7)
        bad=await upload('课程名称,课程编码,上课学期,学期教学次数,课程负责人（工号）\nGood,D2,2,16,TEST-7\nBad,D3,2,16,UNKNOWN\n')
        self.assertFalse(bad.json()['success'],bad.text)
        self.assertIn('第3行',str(bad.json()))
        self.assertIsNone(self.db.query(Course).filter_by(course_code='D2').first())
        missing_semester=await upload('课程名称,课程编码,学期教学次数\nOld,D4,16\n')
        self.assertFalse(missing_semester.json()['success'],missing_semester.text)
        self.assertIn('上课学期',str(missing_semester.json()))
        current=await upload('课程名称,课程编码,上课学期,学期教学次数\nOld,D4,2,16\n')
        self.assertTrue(current.json()['success'],current.text)
        self.assertEqual(self.db.query(Course).filter_by(course_code='D4').one().semester,2)


    async def test_first_login_can_read_course_group_options_before_setup(self):
        from app.models.teacher import Teacher
        from app.services.teacher_accounts import provision_teacher_account
        provision_teacher_account(self.db,self.db.get(Teacher,7))
        self.db.commit()
        login=await self.client.post('/api/auth/login',json={'username':'TEST-7','password':'123456'})
        self.assertEqual(login.status_code,200,login.text)
        self.assertTrue(login.json()['user']['password_change_required'])
        h={'Authorization':'Bearer '+login.json()['access_token']}
        options=await self.client.get('/api/planning/self-profile/course-groups',headers=h)
        self.assertEqual(options.status_code,200,options.text)


class CourseLeaderMigrationTests(unittest.TestCase):
    def test_existing_sqlite_upgrade_is_idempotent_and_preserves_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            engine=create_engine('sqlite:///'+str(Path(folder)/'old.db'))
            with engine.begin() as conn:
                conn.execute(text('CREATE TABLE teachers (id INTEGER PRIMARY KEY)'))
                conn.execute(text('CREATE TABLE courses (id INTEGER PRIMARY KEY, name TEXT, semester_sessions INTEGER, weekly_sessions INTEGER, hours_per_session INTEGER)'))
                conn.execute(text("INSERT INTO courses VALUES (1,'Existing',16,1,2)"))
            _migrate_course_columns(engine);_migrate_course_columns(engine)
            with engine.connect() as conn:
                self.assertEqual(tuple(conn.execute(text('SELECT name, leader_teacher_id FROM courses')).one()),('Existing',None))
            engine.dispose()
