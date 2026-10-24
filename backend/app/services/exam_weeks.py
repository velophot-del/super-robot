"""按年级配置考试周；未配置时沿用旧的“最后一周为考试周”。"""
import re


def _scope_key(value):
    text=str(value or '').strip()
    match=re.fullmatch(r'(\d{4})(?:级|届)?',text)
    return match.group(1) if match else text


def _canonical_config(raw):
    result={}
    for key,values in (raw or {}).items():
        normalized=_scope_key(key)
        result[normalized]=sorted(set(result.get(normalized,[]) or [])|{int(value) for value in (values or [])})
    return result


def normalize_exam_weeks(raw, weeks):
    result = {}
    for key, values in (raw or {}).items():
        key = _scope_key(key)
        if not key:
            continue
        cleaned = set()
        for value in values or []:
            try:
                week = int(value)
            except (TypeError, ValueError):
                raise ValueError('考试周必须为整数')
            if not 1 <= week <= int(weeks):
                raise ValueError(f'考试周{week}超出周期范围1—{int(weeks)}')
            cleaned.add(week)
        result[key] = sorted(set(result.get(key,[]))|cleaned)
    return result


def exam_weeks_from_config(config, settings=None, cohort=None, group=None, weeks=None):
    total = int(weeks or 20)
    if config is None:
        return {total}
    if not config:
        return set()
    normalized=_canonical_config(config)
    for key in (_scope_key(cohort), _scope_key((settings or {}).get('cohort')), str(group or '').strip(), '*'):
        if key and key in normalized:
            return {int(week) for week in normalized[key] if 1 <= int(week) <= total}
    return {total}


def exam_weeks_for(plan_or_settings, cohort=None, group=None, weeks=None):
    settings = getattr(plan_or_settings, 'settings', plan_or_settings) or {}
    total = weeks or getattr(plan_or_settings, 'weeks', None) or 20
    normalized_cohort = _scope_key(cohort)
    central = settings.get('cohort_calendar_rules') or {}
    if normalized_cohort in central:
        rule = central[normalized_cohort]
        limit = min(int(rule.get('weeks') or total), int(total))
        return {int(week) for week in (rule.get('exam_weeks') or []) if 1 <= int(week) <= limit}
    return exam_weeks_from_config(settings.get('exam_weeks'), settings, cohort, group, total)
