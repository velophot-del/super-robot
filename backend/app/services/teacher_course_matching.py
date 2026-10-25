from app.services.stage_planning import capacity
from app.services.matching_weights import get_match_weights, weights_total


def score_candidate(db, plan, task, teacher_id, profile, chosen):
    reasons, weekly = capacity(db, plan, task, teacher_id, profile, chosen)
    weights = get_match_weights(plan); maximum = weights_total(weights)
    complete = bool((profile.get('verified') or profile.get('professional_profile_source')=='self_declared') and task.get('profile_verified') and
                    profile.get('direction') and profile.get('tags') and task.get('direction') and task.get('tags'))
    direction_match = complete and profile['direction'].strip().casefold() == task['direction'].strip().casefold()
    required = {t.strip().casefold() for t in task.get('tags', [])}
    actual = {t.strip().casefold() for t in profile.get('tags', [])}
    hits = sorted(required & actual)
    fit_direction = 20 if direction_match else 0
    fit_domain = round(15*len(hits)/len(required), 2) if complete else None
    domain = round(weights['domain']*len(hits)/len(required), 2) if complete else None
    limit = profile.get('weekly_limit', 20)
    headroom = min((limit-weekly[w]-profile.get('external_hours', {}).get(str(w), 0)
                    for w in weekly), default=limit)
    components = [
        {'name': '团队成员', 'score': weights['team'] if profile.get('verified') and task['code'] in profile.get('team_codes', []) else 0, 'maximum': weights['team']},
        {'name': '专业方向', 'score': weights['direction'] if direction_match else (None if not complete else 0), 'maximum': weights['direction']},
        {'name': '领域命中', 'score': domain, 'maximum': weights['domain'], 'hits': hits},
        {'name': '曾授课程', 'score': weights['taught'] if profile.get('verified') and task['code'] in profile.get('taught_codes', []) else 0, 'maximum': weights['taught']},
        {'name': '剩余容量', 'score': round(weights['capacity']*max(0, min(1,headroom/limit)),2) if limit else 0, 'maximum': weights['capacity']},
    ]
    raw = round(sum(c['score'] for c in components),2) if complete else None
    skilled={str(value).strip().casefold() for value in profile.get('skilled_courses',[])}
    source=profile.get('professional_profile_source','admin_verified' if profile.get('verified') else 'unknown')
    explanation = _build_explanation(
        complete=complete, source=source, direction_match=direction_match, hits=hits,
        team_hit=bool(components[0]['score']), taught_hit=bool(components[3]['score']),
        headroom=headroom, limit=limit,
        professional_fit=round((fit_direction+(fit_domain or 0))/35*100,1) if complete else None,
        raw=raw, maximum=maximum)
    return {'skilled_course_match':task['name'].strip().casefold() in skilled or task['code'].strip().casefold() in skilled,
            'professional_profile_source':source, 'task_id': task['id'], 'teacher_id': teacher_id,
            'professional_fit': round((fit_direction+(fit_domain or 0))/35*100,1) if complete else None,
            'raw_total': raw, 'normalized_total': round(raw/maximum*100,1) if raw is not None else None,
            'maximum': maximum, 'match_weights': weights,
            'complete': complete, 'eligible': not reasons, 'reasons': reasons,
            'components': components, 'profile': profile,
            'explanation': explanation}


def _build_explanation(complete, source, direction_match, hits, team_hit, taught_hit,
                       headroom, limit, professional_fit, raw, maximum):
    """为单个候选生成可读的自然语言推荐理由（确定性，不依赖外部服务）。

    在规则评分的基础上把“为什么推荐这位教师”说清楚，供审核人直接采信。
    """
    if not complete:
        return '教师或课程画像资料不足，待核实，不自动推荐'
    signals = []
    if direction_match:
        signals.append('专业方向一致')
    if hits:
        signals.append('领域命中「%s」' % '、'.join(hits))
    if team_hit:
        signals.append('属课程团队成员')
    if taught_hit:
        signals.append('曾授过该课程')
    if limit and headroom >= 4:
        signals.append('课时余量充足')
    elif limit:
        signals.append('课时余量偏紧')
    rationale = '；'.join(signals) if signals else '与课程画像无显著关联'
    source_note = '教师自填资料' if source == 'self_declared' else '已核实资料'
    score_note = ''
    if raw is not None and maximum:
        normalized = round(raw / maximum * 100, 1)
        score_note = f'，综合推荐 {normalized}%（{raw}/{maximum}）'
    fit_note = f'专业适配度 {professional_fit}%' if professional_fit is not None else ''
    return f'{source_note}：{rationale}。{fit_note}{score_note}。'
