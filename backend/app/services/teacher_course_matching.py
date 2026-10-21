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
    return {'skilled_course_match':task['name'].strip().casefold() in skilled or task['code'].strip().casefold() in skilled,
            'professional_profile_source':source, 'task_id': task['id'], 'teacher_id': teacher_id,
            'professional_fit': round((fit_direction+(fit_domain or 0))/35*100,1) if complete else None,
            'raw_total': raw, 'normalized_total': round(raw/maximum*100,1) if raw is not None else None,
            'maximum': maximum, 'match_weights': weights,
            'complete': complete, 'eligible': not reasons, 'reasons': reasons,
            'components': components, 'profile': profile,
            'explanation': ('专业资料由教师自填，团队和曾授记录按管理员核实结果计分' if source=='self_declared' else '资料已核对，按规则评分') if complete else '教师或课程画像资料不足，待核实，不自动推荐'}
