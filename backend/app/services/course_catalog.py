"""课程库到当前排课周期的适用范围解析。"""
from app.models.class_info import ClassInfo
from app.models.course import Course
from app.services.academic_scope import (
    MAX_UNDERGRADUATE_SEMESTER,
    cohort_matches,
    department_matches,
    program_semester,
)
from app.services.course_library import is_public_course


def courses_for_group(db, group, semester, courses=None):
    """返回适用于单个教学班和培养学期的活动课程。"""
    rows = courses if courses is not None else db.query(Course).filter(Course.is_active.is_(True)).all()
    result = []
    for course in rows:
        if is_public_course(course.course_type):
            continue
        if course.semester != semester:
            continue
        if course.cohort and not cohort_matches(group.grade, course.cohort):
            continue
        if course.department and not department_matches(course.department, group.department or ''):
            continue
        result.append(course)
    return result


def course_catalog_scope(db, start_date, term, allowed_groups=None, major=None, cohort=None, semester=None):
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
        current_semester = semester or program_semester(start_date, term, group.grade)
        if not current_semester or current_semester > MAX_UNDERGRADUATE_SEMESTER:
            continue
        applicable = courses_for_group(db, group, current_semester, active_courses)
        if applicable:
            scope.append({'class': group, 'semester': current_semester, 'courses': applicable})
    return scope


def effective_teaching_weeks(course):
    """课程授课周数：优先使用教学计划值；缺失时按学期次数÷每周次数向上取整。"""
    if course.teaching_weeks:
        return course.teaching_weeks
    weekly = max(course.weekly_sessions or 1, 1)
    return max(1, ((course.semester_sessions or 0) + weekly - 1) // weekly)


def course_pool_rows(scope):
    """生成甘特图课程池需要的扁平课程—班级行。"""
    rows = []
    for item in scope:
        group = item['class']
        semester = item['semester']
        for course in item['courses']:
            rows.append({
                'id': course.id,
                'document_id': None,
                'major': group.department or course.department or '',
                'cohort': group.grade,
                'semester': semester,
                'groups': [group.name],
                'name': course.name,
                'code': course.course_code,
                'credits': course.credits,
                'required_hours': course.total_hours or course.semester_sessions * course.hours_per_session,
                'course_type': course.course_type,
                'course_nature': course.course_nature,
                'teaching_weeks': effective_teaching_weeks(course),
                'weekly_hours': course.weekly_sessions * course.hours_per_session,
                'tail_hours': course.tail_hours,
                'direction': '',
                'tags': [],
                'notes': course.remarks or '',
                'schedulable': True,
            })
    return rows
