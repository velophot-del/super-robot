"""教师专业画像自动构建：从历史授课记录与现有资料中抽取方向、领域与擅长课程。

规则版始终可用：按授课频次聚合方向、领域标签和擅长课程。
AI 版：在规则版基础上让模型润色并给出可读的理由；任何失败回退规则版。
"""
import json
from collections import Counter

from app.models.course import Course
from app.models.teacher import Teacher
from app.models.planning import TeachingAssignment, TeachingTask, TeacherProfile
from app.models.schedule import ScheduleEntry
from app.services.ai_config import LLMError, call_llm, resolve_config

DIRECTIONS = ['视觉传达设计', '包装设计', '智能交互设计', '数字艺术', '时尚传播']

SYSTEM_PROMPT = """你是学院教务系统的教师画像助手。根据教师的历史授课记录，为教师画像给出专业方向、领域标签和擅长课程。
要求：
- 专业方向从给定方向列表中选择最匹配的一个；若都不匹配，用与教师所属部门一致的名称。
- 领域标签 2 到 4 个，来自课程名称/方向的合理归纳，不编造。
- 擅长课程 2 到 5 门，取自历史授课记录中的课程名称。
- 只用给定数据，不确定就少给而不是编造。
- 只输出 JSON：{"direction":"","tags":[],"skilled_courses":[],"rationale":"两句话说明依据"}"""


def teaching_history(db, teacher_id):
    """汇总该教师的历史授课记录（新版阶段计划 + 旧版历史课表）。"""
    courses = []
    seen = set()

    # 新版阶段计划：已锁定分配的课程任务
    rows = (db.query(TeachingAssignment, TeachingTask)
            .join(TeachingTask, TeachingAssignment.task_id == TeachingTask.id)
            .filter(TeachingAssignment.locked.is_(True))
            .order_by(TeachingTask.id)
            .all())
    for assignment, task in rows:
        if teacher_id not in (assignment.teacher_ids or []):
            continue
        if ('task', task.id) in seen:
            continue
        seen.add(('task', task.id))
        payload = task.payload or {}
        courses.append({'name': payload.get('name', ''),
                        'code': payload.get('code', ''),
                        'direction': payload.get('direction', ''),
                        'tags': payload.get('tags') or [],
                        'source': '阶段计划'})

    # 旧版排课：历史课表里的课程
    for entry in db.query(ScheduleEntry).filter(ScheduleEntry.teacher_id == teacher_id).all():
        course = db.get(Course, entry.course_id)
        if not course or ('course', course.id) in seen:
            continue
        seen.add(('course', course.id))
        courses.append({'name': course.name or '',
                        'code': course.course_code or '',
                        'direction': course.department or '',
                        'tags': [],
                        'source': '历史课表'})
    return courses


def rule_based_proposal(teacher, history):
    """确定性聚合，作为兜底与初始建议。"""
    dir_counter = Counter(c['direction'] for c in history if c.get('direction'))
    tag_counter = Counter(t for c in history for t in (c.get('tags') or []))
    direction = dir_counter.most_common(1)[0][0] if dir_counter else (teacher.department or '')
    tags = [t for t, _ in tag_counter.most_common(4)]
    skilled_courses = list(dict.fromkeys(c['name'] for c in history if c.get('name')))
    taught_codes = list(dict.fromkeys(c['code'] for c in history if c.get('code')))
    rationale = (f"依据 {len(history)} 条历史授课记录：主要方向「{direction}」，"
                 f"授课 {len(taught_codes)} 门（{'、'.join(taught_codes[:4]) or '暂无'}）。")
    return {
        'direction': direction,
        'tags': tags,
        'skilled_courses': skilled_courses,
        'team_codes': [],
        'taught_codes': taught_codes,
        'rationale': rationale,
    }


def _parse_proposal(text):
    text = (text or '').strip()
    if text.startswith('```'):
        parts = text.split('\n', 1)
        text = parts[1] if len(parts) > 1 else ''
        if text.rstrip().endswith('```'):
            text = text.rstrip()[:-3]
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('AI 未返回有效 JSON')
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError('AI 未返回有效 JSON')
    return data


def build_profile_proposal(db, teacher_id):
    """返回画像建议：{proposal, history, source, rationale}。

    未配置 AI 时使用规则聚合；配置了 AI 则让模型润色，失败回退规则版。
    """
    teacher = db.get(Teacher, teacher_id)
    if teacher is None:
        raise ValueError('教师不存在')
    history = teaching_history(db, teacher_id)
    rule = rule_based_proposal(teacher, history)

    config = resolve_config(db)
    if db is not None:
        db.rollback()
    if not config or not config.get('api_key'):
        return {'proposal': rule, 'history': history, 'source': 'rules',
                'reason': '未配置 AI 服务，已使用规则汇总'}

    payload = {
        'teacher': {'name': teacher.name, 'department': teacher.department,
                    'title': teacher.title, 'directions_available': DIRECTIONS},
        'history': [{'name': c['name'], 'code': c['code'], 'direction': c['direction'],
                     'tags': c['tags'], 'source': c['source']} for c in history],
        'rule_proposal': rule,
    }
    user_text = '历史授课记录与规则建议如下：\n' + json.dumps(payload, ensure_ascii=False)
    try:
        result = call_llm(config, SYSTEM_PROMPT, user_text, max_tokens=1000, json_mode=True)
        ai = _parse_proposal(result.get('text', ''))
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        return {'proposal': rule, 'history': history, 'source': 'rules',
                'reason': f'{exc}，已使用规则汇总'}

    proposal = {
        'direction': str(ai.get('direction') or rule['direction']),
        'tags': [str(t) for t in (ai.get('tags') or []) if isinstance(t, str)][:6] or rule['tags'],
        'skilled_courses': [str(c) for c in (ai.get('skilled_courses') or []) if isinstance(c, str)][:10] or rule['skilled_courses'],
        'team_codes': rule['team_codes'],
        'taught_codes': rule['taught_codes'],
        'rationale': str(ai.get('rationale') or rule['rationale']),
    }
    return {'proposal': proposal, 'history': history, 'source': 'llm',
            'provider': config.get('provider'), 'model': result.get('model')}
