"""针对审查修复项的回归测试。"""
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.schedule import ScheduleEntry
from app.services.conflict import ConflictDetector
from app.services.curriculum_materials import extract_rows
from app.services.schedule_versions import resolve_schedule_version
from app.services.scheduler import SchedulingEngine
from app.utils.departments import merge_department, split_departments


class ConflictWeekAggregationTests(unittest.TestCase):
    def test_multi_week_schedule_does_not_report_daily_overload(self):
        entries = []
        for week in range(1, 17):
            entries.append({
                "id": week,
                "course_id": 1,
                "teacher_id": 1,
                "class_id": 1,
                "classroom_id": 1,
                "week_number": week,
                "day_of_week": 1,
                "period_start": 1,
                "period_end": 2,
            })

        hard, soft, _stats = ConflictDetector(entries).detect_all()

        self.assertEqual(hard, [])
        self.assertEqual(
            [c for c in soft if c["category"] == "time"], [],
            "同一门课每周 2 课时不应被跨周累加成每日 32 课时",
        )


class CurriculumCodeScopeTests(unittest.TestCase):
    def test_generated_codes_differ_between_majors(self):
        content = "课程名称,学分,总学时,开课学期\n素描,2,32,1\n".encode("utf-8")

        design, design_errors = extract_rows("scheme.csv", content, "Design|2026|1")
        painting, painting_errors = extract_rows("scheme.csv", content, "Painting|2026|1")

        self.assertEqual(design_errors, [])
        self.assertEqual(painting_errors, [])
        self.assertTrue(design[0]["code"].startswith("SYS-"))
        self.assertNotEqual(design[0]["code"], painting[0]["code"])


class DepartmentMergeTests(unittest.TestCase):
    def test_shared_course_keeps_all_departments(self):
        self.assertEqual(split_departments("Design,Painting"), ["Design", "Painting"])
        self.assertEqual(merge_department("Design", "Painting"), "Design,Painting")
        self.assertEqual(merge_department("Design", "Design"), "Design")
        # 空专业代表通用课程，不应被导入收窄
        self.assertIsNone(merge_department(None, "Design"))


class SchedulerEngineTests(unittest.TestCase):
    @staticmethod
    def _base_data():
        courses = [{
            "id": 1, "name": "素描", "weekly_sessions": 1,
            "semester_sessions": 2, "requires_consecutive": False,
            "requires_lab": False, "department": "Design",
        }]
        teachers = [{
            "id": 1, "name": "张老师", "department": "Design",
            "max_weekly_hours": 20,
        }]
        classes = [
            {"id": 1, "name": "设计1班", "student_count": 30, "department": "Design"},
            {"id": 2, "name": "设计2班", "student_count": 30, "department": "Design"},
        ]
        rooms = [{"id": 1, "name": "A101", "capacity": 60, "room_type": "普通教室"}]
        return courses, teachers, classes, rooms

    def test_course_keeps_one_teaching_class_and_teacher(self):
        engine = SchedulingEngine({"population_size": 1, "max_generations": 1})
        engine.load_data(*self._base_data())

        schedule = engine._create_random_schedule()

        self.assertTrue(schedule.assignments)
        self.assertEqual(len({a.class_id for a in schedule.assignments}), 1)
        self.assertEqual(len({a.teacher_id for a in schedule.assignments}), 1)

    def test_active_capacity_rule_is_enforced(self):
        courses, teachers, classes, rooms = self._base_data()
        for class_info in classes:
            class_info["student_count"] = 40
        rooms[0]["capacity"] = 35

        engine = SchedulingEngine({"population_size": 1, "max_generations": 1})
        engine.load_data(
            courses, teachers, classes, rooms,
            constraints=[{
                "id": 1, "name": "教室容量匹配", "rule_type": "hard",
                "category": "classroom", "weight": 8.0, "penalty_score": 50.0,
                "is_active": True,
                "rule_expression": ('{"type": "compare", "field1": "room_capacity", '
                                    '"field2": "student_count", "op": "gte"}'),
            }],
        )

        schedule = engine._create_random_schedule()
        self.assertGreaterEqual(schedule.hard_violations, 1)

    def test_disabled_capacity_rule_turns_off_default_check(self):
        courses, teachers, classes, rooms = self._base_data()
        for class_info in classes:
            class_info["student_count"] = 40
        rooms[0]["capacity"] = 35

        engine = SchedulingEngine({"population_size": 1, "max_generations": 1})
        engine.load_data(
            courses, teachers, classes, rooms,
            constraints=[{
                "id": 1, "name": "教室容量匹配", "rule_type": "hard",
                "category": "classroom", "weight": 8.0, "penalty_score": 50.0,
                "is_active": False,
                "rule_expression": ('{"type": "compare", "field1": "room_capacity", '
                                    '"field2": "student_count", "op": "gte"}'),
            }],
        )

        schedule = engine._create_random_schedule()
        self.assertEqual(schedule.hard_violations, 0)


class ScheduleVersionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_omitted_version_resolves_to_latest(self):
        for version, entry_id in (("schedule_100_aaaaaaaa", 1),
                                  ("schedule_200_bbbbbbbb", 2)):
            self.db.add(ScheduleEntry(
                id=entry_id, schedule_version=version,
                course_id=1, teacher_id=1, class_id=1, classroom_id=1,
                week_number=1, day_of_week=1, period_start=1, period_end=1,
            ))
        self.db.commit()

        self.assertEqual(resolve_schedule_version(self.db, None),
                         "schedule_200_bbbbbbbb")
        self.assertEqual(resolve_schedule_version(self.db, "schedule_100_aaaaaaaa"),
                         "schedule_100_aaaaaaaa")


if __name__ == "__main__":
    unittest.main()
