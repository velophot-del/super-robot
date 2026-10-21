"""按年级配置考试周；未配置时沿用旧的“最后一周为考试周”。"""


def normalize_exam_weeks(raw, weeks):
    result = {}
    for key, values in (raw or {}).items():
        key = str(key).strip()
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
        result[key] = sorted(cleaned)
    return result


def exam_weeks_from_config(config, settings=None, cohort=None, group=None, weeks=None):
    total = int(weeks or 20)
    if config is None:
        return {total}
    if not config:
        return set()
    for key in (cohort, (settings or {}).get('cohort'), group, '*'):
        if key and str(key) in config:
            return {int(week) for week in config[str(key)] if 1 <= int(week) <= total}
    return {total}


def exam_weeks_for(plan_or_settings, cohort=None, group=None, weeks=None):
    settings = getattr(plan_or_settings, 'settings', plan_or_settings) or {}
    total = weeks or getattr(plan_or_settings, 'weeks', None) or 20
    return exam_weeks_from_config(settings.get('exam_weeks'), settings, cohort, group, total)
