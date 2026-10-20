from app.services.stage_planning import capacity


def score_candidate(db, plan, task, teacher_id, profile, rank, chosen):
    reasons, weekly = capacity(db, plan, task, teacher_id, profile, chosen)
    complete = bool((profile.get('verified') or profile.get('professional_profile_source')=='self_declared') and task.get('profile_verified') and
                    profile.get('direction') and profile.get('tags') and task.get('direction') and task.get('tags'))
    direction = 20 if complete and profile['direction'].strip().casefold() == task['direction'].strip().casefold() else 0
    required = {t.strip().casefold() for t in task.get('tags', [])}
    actual = {t.strip().casefold() for t in profile.get('tags', [])}
    hits = sorted(required & actual)
    domain = round(15*len(hits)/len(required), 2) if complete else None
    limit = profile.get('weekly_limit', 20)
    headroom = min((limit-weekly[w]-profile.get('external_hours', {}).get(str(w), 0)
                    for w in weekly), default=limit)
    components = [
        {'name': '团队成员', 'score': 40 if profile.get('verified') and task['code'] in profile.get('team_codes', []) else 0, 'maximum': 40},
        {'name': '专业方向', 'score': direction if complete else None, 'maximum': 20},
        {'name': '领域命中', 'score': domain, 'maximum': 15, 'hits': hits},
        {'name': '曾授课程', 'score': 15 if profile.get('verified') and task['code'] in profile.get('taught_codes', []) else 0, 'maximum': 15},
        {'name': '志愿顺序', 'score': [10,7,5,3,1][min(rank,4)], 'maximum': 10},
        {'name': '剩余容量', 'score': round(5*max(0, min(1,headroom/limit)),2) if limit else 0, 'maximum': 5},
    ]
    raw = round(sum(c['score'] for c in components),2) if complete else None
    skilled={str(value).strip().casefold() for value in profile.get('skilled_courses',[])}
    source=profile.get('professional_profile_source','admin_verified' if profile.get('verified') else 'unknown')
    return {'skilled_course_match':task['name'].strip().casefold() in skilled or task['code'].strip().casefold() in skilled,
            'professional_profile_source':source, 'task_id': task['id'], 'teacher_id': teacher_id, 'rank': rank+1,
            'professional_fit': round((direction+domain)/35*100,1) if complete else None,
            'raw_total': raw, 'normalized_total': round(raw/105*100,1) if raw is not None else None,
            'complete': complete, 'eligible': not reasons, 'reasons': reasons,
            'components': components, 'profile': profile,
            'explanation': ('专业资料由教师自填，团队和曾授记录按管理员核实结果计分' if source=='self_declared' else '资料已核对，按规则评分') if complete else '教师或课程画像资料不足，待核实，不自动推荐'}
