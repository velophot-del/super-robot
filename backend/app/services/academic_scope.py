"""全学院排课周期的学年、学期与培养方案范围计算。"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

MAX_UNDERGRADUATE_SEMESTER = 8


def current_academic_term(value=None) -> int:
    """按学院学年口径推断当前学期：8月至次年1月为第一学期。"""
    value = value or datetime.now(ZoneInfo('Asia/Shanghai')).date()
    return 1 if value.month >= 8 or value.month == 1 else 2


def academic_start_year(value) -> int:
    """8月至次年7月为一个学年，返回该学年的起始年份。"""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.year if value.month >= 8 else value.year - 1


def plan_term(plan_or_settings) -> int:
    """周期学期：优先使用全局周期的 term，旧周期沿用培养学期奇偶。"""
    settings = getattr(plan_or_settings, 'settings', plan_or_settings) or {}
    term = settings.get('term')
    if term in (1, 2):
        return int(term)
    semester = settings.get('semester', 2)
    try:
        return 1 if int(semester) % 2 else 2
    except (TypeError, ValueError):
        return 2


def is_global(plan_or_settings) -> bool:
    """未绑定单一专业/届次的周期即为全学院周期。"""
    settings = getattr(plan_or_settings, 'settings', plan_or_settings) or {}
    return bool(settings.get('global')) or (not settings.get('major') and not settings.get('cohort'))


def program_semester(start_date, term: int, cohort) -> int | None:
    """按入学年级与全局学期推算培养方案学期，例如 2026 级在 2026-2027 第2学期 = 2。"""
    try:
        value = str(cohort).strip().removesuffix('级').removesuffix('届')
        year = int(value)
        if 0 <= year < 100:
            year += 2000
    except (TypeError, ValueError):
        return None
    semester = (academic_start_year(start_date) - year) * 2 + int(term)
    return semester if 1 <= semester <= 20 else None


def curriculum_semester(document, start_date, term: int) -> int | None:
    """仅返回培养方案学制内且有可排课程的当前学期。"""
    semester = program_semester(start_date, term, document.cohort)
    duration = getattr(document, 'duration_semesters', None) or MAX_UNDERGRADUATE_SEMESTER
    if semester is None or semester > duration:
        return None
    for row in document.rows:
        if not row.get('schedulable', True):
            continue
        try:
            if int(row.get('semester')) == semester:
                return semester
        except (TypeError, ValueError):
            continue
    return None


def cohort_matches(grade, cohort) -> bool:
    """班级年级与培养方案年级匹配，兼容两位年份及历史后缀。"""
    def year(value):
        value = str(value or '').strip().removesuffix('级').removesuffix('届')
        digits = value[:4] if len(value) >= 4 and value[:4].isdigit() else value
        if digits.isdigit():
            parsed = int(digits)
            return parsed + 2000 if 0 <= parsed < 100 else parsed
        return None

    grade_year = year(grade)
    cohort_year = year(cohort)
    if grade_year is not None and cohort_year is not None:
        return grade_year == cohort_year
    grade = str(grade or '').strip()
    cohort = str(cohort or '').strip()
    if not grade or not cohort:
        return False
    return grade == cohort


def grade_label(value) -> str:
    """规范显示年级后缀，并保留两位或四位年份。"""
    text = str(value or '').strip()
    if not text or text.startswith('未设置'):
        return text or '未设置年级'
    return text.removesuffix('届').removesuffix('级') + '级'


def department_matches(department, major: str) -> bool:
    """按精确名称或明确的多专业分隔字段匹配，不用子串猜测专业归属。"""
    from app.utils.departments import split_departments
    return str(major or '').strip() in split_departments(department)


def groups_for_curriculum(db, major: str, cohort: str, allowed: list[str] | None = None,
                          program_id: int | None = None) -> list[str]:
    """从班级基础数据中找出属于某培养方案（专业+年级）的教学组。"""
    from app.models.class_info import ClassInfo
    names = [row.name for row in db.query(ClassInfo).filter(ClassInfo.is_active.is_(True)).order_by(
                ClassInfo.grade, ClassInfo.department, ClassInfo.name)
             if (not program_id or not getattr(row, 'program_id', None) or row.program_id == program_id) and
             department_matches(row.department, major) and cohort_matches(row.grade, cohort)]
    if allowed:
        permitted = set(allowed)
        names = [name for name in names if name in permitted]
    return names


def groups_for_cycle(db, start_date, term: int, start_dates_by_cohort=None) -> list[str]:
    """按标准八学期学制筛选当前仍在读的有效班级。"""
    from app.models.class_info import ClassInfo
    from app.services.cohort_calendar import normalize_cohort
    cohort_dates = start_dates_by_cohort or {}
    return [row.name for row in db.query(ClassInfo).filter(ClassInfo.is_active.is_(True)).order_by(
        ClassInfo.grade, ClassInfo.department, ClassInfo.name)
        if 1 <= (program_semester(cohort_dates.get(normalize_cohort(row.grade), start_date), term, row.grade) or 0) <= MAX_UNDERGRADUATE_SEMESTER]


def groups_in_cycle(db, plan) -> list[str]:
    """保留周期原快照中的自定义组，但过滤已毕业或失效的班级。"""
    from app.models.class_info import ClassInfo

    settings = getattr(plan, 'settings', None) or {}
    from app.services.cohort_calendar import cohort_start_dates
    eligible = set(groups_for_cycle(db, plan.start_date, plan_term(plan), cohort_start_dates(db, plan)))
    known = {row.name for row in db.query(ClassInfo)}
    return [group for group in settings.get('groups', []) if group in eligible or group not in known]
