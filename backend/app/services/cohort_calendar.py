"""按年级读取管理员维护的开课日历规则。"""
import re

from app.models.planning import CohortCalendarRule


def normalize_cohort(value):
    match = re.fullmatch(r'\s*(\d{4})(?:级|届)?\s*', str(value or ''))
    return match.group(1) if match else str(value or '').strip()


def cohort_calendar_rule(db, cohort):
    key = normalize_cohort(cohort)
    return db.get(CohortCalendarRule, key) if key else None


def _rule_for_plan(db, plan, cohort):
    key = normalize_cohort(cohort)
    if not key:
        return None
    if getattr(plan, 'state', None) == 'published':
        from app.models.planning import PublishedPlan
        snapshot = db.query(PublishedPlan).filter_by(plan_id=plan.id).order_by(PublishedPlan.id.desc()).first()
        frozen = ((snapshot.payload.get('plan') or {}).get('cohort_calendar_rules') or {}).get(key) if snapshot else None
        if frozen:
            return frozen
    return cohort_calendar_rule(db, key)


def _value(rule, key):
    return rule.get(key) if isinstance(rule, dict) else getattr(rule, key)


def calendar_rule_payload(row):
    return {
        'cohort': row.cohort,
        'weeks': row.weeks,
        'start_date': row.start_date.isoformat(),
        'exam_weeks': list(row.exam_weeks or []),
        'revision': row.revision,
        'configured': True,
    }


def cohort_weeks(db, plan, cohort):
    rule = _rule_for_plan(db, plan, cohort)
    return min(int(_value(rule, 'weeks')), int(plan.weeks)) if rule else plan.weeks


def cohort_start_date(db, plan, cohort):
    rule = _rule_for_plan(db, plan, cohort)
    if not rule:
        return plan.start_date
    value = _value(rule, 'start_date')
    from datetime import date
    return date.fromisoformat(value) if isinstance(value, str) else value


def cohort_start_dates(db, plan):
    from app.models.class_info import ClassInfo
    cohorts = {normalize_cohort(row.grade) for row in db.query(ClassInfo.grade).filter(
        ClassInfo.grade.is_not(None)).distinct() if normalize_cohort(row.grade)}
    return {cohort: cohort_start_date(db, plan, cohort) for cohort in cohorts}


def cohort_exam_weeks(db, plan, cohort, group=None):
    rule = _rule_for_plan(db, plan, cohort)
    if rule:
        total = min(int(_value(rule, 'weeks')), int(plan.weeks))
        return {int(week) for week in (_value(rule, 'exam_weeks') or []) if 1 <= int(week) <= total}
    from app.services.exam_weeks import exam_weeks_for
    return exam_weeks_for(plan, cohort, group, plan.weeks)
