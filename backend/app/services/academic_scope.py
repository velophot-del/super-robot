"""全学院排课周期的学年、学期与培养方案范围计算。"""
from datetime import date


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
    """未绑定单一专业/年级的周期即为全学院周期。"""
    settings = getattr(plan_or_settings, 'settings', plan_or_settings) or {}
    return bool(settings.get('global')) or (not settings.get('major') and not settings.get('cohort'))


def program_semester(start_date, term: int, cohort) -> int | None:
    """按入学届次与全局学期推算培养方案学期，例如 2026 级在 2026-2027 第2学期 = 2。"""
    try:
        year = int(str(cohort).strip()[:4])
    except (TypeError, ValueError):
        return None
    semester = (academic_start_year(start_date) - year) * 2 + int(term)
    return semester if 1 <= semester <= 12 else None


def cohort_matches(grade, cohort) -> bool:
    """班级年级与培养方案届次匹配：支持“2026”及以届次开头的年级文本。"""
    grade = str(grade or '').strip()
    cohort = str(cohort or '').strip()
    if not grade or not cohort:
        return False
    return grade == cohort or (grade.isdigit() and cohort.isdigit() and grade[:4] == cohort[:4])


def department_matches(department, major: str) -> bool:
    """专业名称允许学院名中包含专业名等常见写法差异。"""
    department = str(department or '').strip()
    major = str(major or '').strip()
    return bool(department and major and
                (department == major or department in major or major in department))


def groups_for_curriculum(db, major: str, cohort: str, allowed: list[str] | None = None) -> list[str]:
    """从班级基础数据中找出属于某培养方案（专业+届次）的教学组。"""
    from app.models.class_info import ClassInfo
    names = [row.name for row in db.query(ClassInfo).order_by(ClassInfo.id)
             if department_matches(row.department, major) and cohort_matches(row.grade, cohort)]
    if allowed:
        permitted = set(allowed)
        names = [name for name in names if name in permitted]
    return names
