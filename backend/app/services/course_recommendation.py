"""教师选课智能推荐：基于教师画像为开放周期的课程任务打分并给出推荐理由。

规则版始终可用：按专业方向、领域命中、擅长课程三个维度确定性打分。
AI 版：把推荐结果组织成一句友好的开场说明；失败回退规则说明。
"""
import json

from app.models.planning import TeacherProfile, TeachingTask
from app.services.ai_config import LLMError, call_llm, resolve_config
from app.services.personal_profile import effective_profile
from app.services.stage_planning import task_dict

SYSTEM_PROMPT = """你是学院选课系统的选课助手。根据教师的专业画像和系统推荐的课程，写一句不超过 60 字的开场推荐语。
要求：点名教师画像的 1-2 个关键词，并说明推荐依据（专业方向、领域、擅长课程）。只输出这一句话。"""


def score_for_teacher(profile, task):
    direction = (profile.get('direction') or '').strip().casefold()
    task_direction = (task.get('direction') or '').strip().casefold()
    profile_tags = {x.strip().casefold() for x in (profile.get('tags') or [])}
    task_tags = {x.strip().casefold() for x in (task.get('tags') or [])}
    skilled = {str(x).strip().casefold() for x in (profile.get('skilled_courses') or [])}
    hits = sorted(profile_tags & task_tags)
    direction_match = bool(direction and task_direction and direction == task_direction)
    name = (task.get('name') or '').strip().casefold()
    code = (task.get('code') or '').strip().casefold()
    skilled_match = name in skilled or code in skilled
    score = (20 if direction_match else 0) + len(hits) * 15 + (15 if skilled_match else 0)
    reasons = []
    if direction_match:
        reasons.append('专业方向一致')
    if hits:
        reasons.append(f"领域命中「{'、'.join(hits)}」")
    if skilled_match:
        reasons.append('在您的擅长课程中')
    if not reasons:
        reasons.append('与您的画像部分相关')
    return {'score': score, 'reason': '；'.join(reasons),
            'matched': bool(direction_match or hits or skilled_match)}


def recommend_for_teacher(db, plan, teacher_id, limit=3):
    """返回 top-N 推荐课程与一句总结说明。"""
    record = db.get(TeacherProfile, teacher_id)
    profile = effective_profile(record.payload if record else {})
    rows = db.query(TeachingTask).filter_by(plan_id=plan.id).order_by(TeachingTask.id).all()
    tasks = [task_dict(db, t) for t in rows]
    tasks = [t for t in tasks if t.get('start_week')]

    scored = []
    for task in tasks:
        if teacher_id in (task.get('teacher_ids') or []):
            continue
        result = score_for_teacher(profile, task)
        scored.append({'task_id': task['id'], 'name': task['name'], 'code': task.get('code'),
                       'group': task.get('group'), 'direction': task.get('direction'),
                       'tags': task.get('tags') or [], 'score': result['score'],
                       'reason': result['reason'], 'matched': result['matched']})
    scored.sort(key=lambda x: (-x['score'], x['task_id']))
    top = scored[:max(1, limit)]

    summary = (f"根据您的专业画像（{profile.get('direction') or '未填写方向'} / "
               f"{'、'.join(profile.get('tags') or []) or '未填写领域'}），建议优先考虑以下课程：")
    return {'recommendations': top, 'summary': summary, 'source': 'rules',
            'profile_used': {'direction': profile.get('direction'), 'tags': profile.get('tags'),
                             'skilled_courses': profile.get('skilled_courses')}}


def recommend_with_ai(db, plan, teacher_id, limit=3):
    """推荐结果 + 可选的 AI 开场语；失败回退规则版。"""
    base = recommend_for_teacher(db, plan, teacher_id, limit)
    config = resolve_config(db)
    if db is not None:
        db.rollback()
    if not config or not config.get('api_key') or not base['recommendations']:
        base['reason'] = '未配置 AI 服务，使用规则推荐'
        return base

    payload = {
        'profile': base['profile_used'],
        'courses': [{'name': r['name'], 'direction': r['direction'], 'tags': r['tags'],
                     'reason': r['reason']} for r in base['recommendations']],
    }
    try:
        result = call_llm(config, SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False), max_tokens=300)
        summary = result.get('text', '').strip()
        if summary:
            base['summary'] = summary
            base['source'] = 'llm'
            base['provider'] = config.get('provider')
            base['model'] = result.get('model')
            return base
    except (LLMError, ValueError, TypeError, AttributeError):
        pass
    base['reason'] = 'AI 开场语生成失败，使用规则说明'
    return base
