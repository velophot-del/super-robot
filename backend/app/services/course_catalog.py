"""课程库到当前排课周期的适用范围解析。"""
import math

from app.models.class_info import ClassInfo
from app.models.course import Course
from app.services.academic_scope import (
    MAX_UNDERGRADUATE_SEMESTER,
    cohort_matches,
    department_matches,
    program_semester,
)
from app.services.course_library import is_public_course
from app.services.cohort_calendar import normalize_cohort


def courses_for_group(db, group, semester, courses=None):
    """返回适用于单个教学班和培养学期的活动课程。"""
    rows = courses if courses is not None else db.query(Course).filter(Course.is_active.is_(True)).all()
    result = []
    seen = set()
    for course in sorted(rows, key=lambda row: (row.course_code or "", row.id or 0)):
        if is_public_course(course.course_type):
            continue
        if course.semester != semester:
            continue
        if course.cohort and not cohort_matches(group.grade, course.cohort):
            continue
        if course.program_id or (group.program_id and course.department):
            if not course.program_id or course.program_id != group.program_id:
                continue
        elif course.department and not department_matches(course.department, group.department or ''):
            continue
        if course.direction_id:
            from app.models.planning import AcademicDirection
            direction=db.get(AcademicDirection,course.direction_id)
            course._catalog_direction_name=direction.name if direction else ''
        # 仅编码不同、教学属性完全一致的导入行在同一班级只排一次。
        identity = tuple(getattr(course, field) for field in (
            'semester', 'program_id', 'direction_id', 'offering_unit_id',
            'course_type', 'course_nature', 'total_hours', 'credits',
            'teaching_weeks', 'tail_hours', 'requires_consecutive', 'requires_lab',
            'leader_teacher_id', 'priority', 'remarks')) + (
                course.name.strip().casefold(), normalize_cohort(course.cohort),
                course.department, tuple(course_weekdays(course)))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(course)
    return result


def course_catalog_scope(db, start_date, term, allowed_groups=None, major=None, cohort=None, semester=None,
                         start_dates_by_cohort=None):
    """以课程库的专业、年级和上课学期确定可排班级及课程。"""
    groups = db.query(ClassInfo).filter(ClassInfo.is_active.is_(True)).order_by(
        ClassInfo.grade, ClassInfo.department, ClassInfo.name).all()
    active_courses = db.query(Course).filter(Course.is_active.is_(True)).order_by(
        Course.name, Course.course_code).all()
    allowed = set(allowed_groups or [])
    scope = []
    for group in groups:
        if allowed and group.name not in allowed:
            continue
        if major and not department_matches(major, group.department or ''):
            continue
        if cohort and not cohort_matches(group.grade, cohort):
            continue
        effective_start = (start_dates_by_cohort or {}).get(normalize_cohort(group.grade)) or start_date
        current_semester = semester or program_semester(effective_start, term, group.grade)
        if not current_semester or current_semester > MAX_UNDERGRADUATE_SEMESTER:
            continue
        applicable = courses_for_group(db, group, current_semester, active_courses)
        if applicable:
            scope.append({'class': group, 'semester': current_semester, 'courses': applicable})
    return scope


def course_weekdays(course):
    """课程固定的每周上课日，去重并限制在周一至周日。"""
    days = []
    for value in course.weekdays or []:
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 7 and day not in days:
            days.append(day)
    return sorted(days)


def effective_teaching_weeks(course):
    """课程授课周数：优先使用教学计划值；缺失时按总学时÷每周上课日（每天2节）推算。"""
    if course.teaching_weeks:
        return course.teaching_weeks
    days = len(course_weekdays(course)) or 1
    total = course.total_hours or 0
    return max(1, math.ceil(total / (days * 2))) if total else 1


def course_schedule_info(course):
    """课程的授课周数、每周上课日、计划总学时与周均学时。"""
    days = course_weekdays(course)
    weeks = effective_teaching_weeks(course)
    total = course.total_hours or weeks * max(len(days), 1) * 2
    return {'teaching_weeks': weeks, 'weekdays': days, 'total_hours': total,
            'weekly_hours': math.ceil(total / weeks) if weeks else total}


def course_pool_rows(scope):
    """生成甘特图课程池需要的扁平课程—班级行。"""
    rows = []
    by_key = {}
    for item in scope:
        group = item['class']
        semester = item['semester']
        for course in item['courses']:
            key = (course.id, normalize_cohort(group.grade),
                   (group.department or course.department or '').strip(), semester)
            if key in by_key:
                if group.name not in by_key[key]['groups']:
                    by_key[key]['groups'].append(group.name)
                continue
            info = course_schedule_info(course)
            rows.append({
                'id': course.id,
                'document_id': None,
                'major': group.department or course.department or '',
                'cohort': normalize_cohort(group.grade),
                'semester': semester,
                'groups': [group.name],
                'name': course.name,
                'code': course.course_code,
                'credits': course.credits,
                'required_hours': info['total_hours'],
                'course_type': course.course_type,
                'course_nature': course.course_nature,
                'teaching_weeks': info['teaching_weeks'],
                'weekdays': info['weekdays'],
                'weekly_hours': info['weekly_hours'],
                'tail_hours': course.tail_hours,
                'direction': getattr(course, '_catalog_direction_name', ''),
                'program_id': course.program_id,
                'direction_id': course.direction_id,
                'offering_unit_id': course.offering_unit_id,
                'tags': [],
                'notes': course.remarks or '',
                'schedulable': True,
            })
            by_key[key] = rows[-1]
    return rows
