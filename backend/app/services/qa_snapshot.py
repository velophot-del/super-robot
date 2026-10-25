"""自然语言问答：把管理者的口语问题转成对系统数据的回答。

先构建一个结构化数据快照（教师、课程、教室、计划、负荷、待办），
再让模型仅基于快照回答；未配置 AI 时回退到少量高频问题的规则回答。
"""
import json
from collections import Counter

from app.models.class_info import ClassInfo
from app.models.classroom import Classroom
from app.models.course import Course
from app.models.planning import (AcademicPlan, PreferenceDraft, ScheduleChangeDecision,
                                 ScheduleChangeRequest, TeachingAssignment,
                                 TeachingTask, TeacherProfile)
from app.models.teacher import Teacher
from app.services.ai_config import LLMError, call_llm, resolve_config
from app.services.personal_profile import effective_profile
from app.services.stage_planning import task_dict

SYSTEM_PROMPT = """你是学院排课系统的数据助手。只根据给定的数据快照用中文简洁回答，不要编造数据。
回答控制在 200 字以内，直接给出结论；涉及具体教师或课程时点名说明。"""


def build_snapshot(db):
    """构建问答所需的结构化数据快照。"""
    teachers = db.query(Teacher).order_by(Teacher.id).all()
    courses = db.query(Course).filter(Course.is_active.is_(True)).order_by(Course.id).all()
    classrooms = db.query(Classroom).all()
    classes = db.query(ClassInfo).all()
    plans = db.query(AcademicPlan).order_by(AcademicPlan.id.desc()).all()

    # 教师已锁定授课任务与总学时
    assignments = (db.query(TeachingAssignment, TeachingTask)
                   .join(TeachingTask, TeachingAssignment.task_id == TeachingTask.id)
                   .filter(TeachingAssignment.locked.is_(True)).all())
    teacher_load = {}
    for assignment, task in assignments:
        hours = int((task.payload or {}).get('required_hours') or 0)
        for tid in (assignment.teacher_ids or []):
            entry = teacher_load.setdefault(tid, {'tasks': 0, 'hours': 0, 'courses': []})
            entry['tasks'] += 1
            entry['hours'] += hours
            entry['courses'].append((task.payload or {}).get('name', ''))

    teacher_rows = [{'name': t.name, 'department': t.department, 'title': t.title,
                     'assigned_tasks': teacher_load.get(t.id, {}).get('tasks', 0),
                     'assigned_hours': teacher_load.get(t.id, {}).get('hours', 0)}
                    for t in teachers]
    overloaded = [t for t in teacher_rows if t['assigned_hours'] > (20 * 16)]

    # 活动课程库中尚未进入任何课程任务的课程
    task_codes = {t.payload.get('code') for t in db.query(TeachingTask).all() if t.payload.get('code')}
    unplaced_courses = [{'name': c.name, 'code': c.course_code, 'department': c.department}
                        for c in courses if c.course_code not in task_codes]

    pending_changes = (db.query(ScheduleChangeRequest)
                       .outerjoin(ScheduleChangeDecision, ScheduleChangeDecision.request_id == ScheduleChangeRequest.id)
                       .filter(ScheduleChangeDecision.id.is_(None)).count())

    plan_rows = [{'name': p.name, 'state': p.state, 'revision': p.revision}
                 for p in plans]

    return {
        'teachers': teacher_rows,
        'teachers_total': len(teachers),
        'overloaded_teachers': overloaded,
        'courses_total': len(courses),
        'courses_by_department': dict(Counter(c.department for c in courses if c.department)),
        'unplaced_courses': unplaced_courses,
        'classrooms_total': len(classrooms),
        'classes_total': len(classes),
        'plans': plan_rows,
        'pending_change_requests': pending_changes,
    }


def rule_answer(snapshot, question):
    """未配置 AI 时的兜底：回答少量高频计数问题。"""
    q = question.strip()
    if '教师' in q and ('多少' in q or '几位' in q or '数量' in q):
        return f"当前系统共有 {snapshot['teachers_total']} 位教师。"
    if '课程' in q and ('多少' in q or '几门' in q or '数量' in q):
        return f"活动课程库共有 {snapshot['courses_total']} 门课程。"
    if '教室' in q and ('多少' in q or '几间' in q or '数量' in q):
        return f"当前共有 {snapshot['classrooms_total']} 间教室。"
    if '调课' in q and ('待' in q or '未' in q or '多少' in q or '几' in q):
        return f"当前有 {snapshot['pending_change_requests']} 条调课申请待处理。"
    if '超' in q and '负荷' in q:
        names = '、'.join(t['name'] for t in snapshot['overloaded_teachers']) or '无'
        return f"负荷偏高的教师：{names}。"
    return '未配置 AI 服务，无法回答开放性问题。可配置 AI 后重试；目前仅支持数量类问题。'


def answer_question(db, question):
    """回答自然语言问题；失败回退规则回答。"""
    snapshot = build_snapshot(db)
    config = resolve_config(db)
    if db is not None:
        db.rollback()
    if not config or not config.get('api_key'):
        return {'answer': rule_answer(snapshot, question), 'source': 'rules',
                'snapshot': snapshot, 'reason': '未配置 AI 服务'}

    user_text = ('数据快照：\n' + json.dumps(snapshot, ensure_ascii=False)
                 + '\n\n问题：' + question)
    try:
        result = call_llm(config, SYSTEM_PROMPT, user_text, max_tokens=800)
        answer = result.get('text', '').strip()
        if not answer:
            raise ValueError('AI 未返回内容')
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        return {'answer': rule_answer(snapshot, question), 'source': 'rules',
                'snapshot': snapshot, 'reason': f'{exc}，已回退规则回答'}
    return {'answer': answer, 'source': 'llm', 'provider': config.get('provider'),
            'model': result.get('model'), 'snapshot': snapshot}


TEACHER_SYSTEM_PROMPT = """你是学院排课系统的教师端助手。只根据给定的数据（教师画像、开放周期课程、系统推荐、个人草稿）用中文简洁回答。
回答控制在 150 字以内；涉及课程时点出课程名和理由。如果问题与数据无关，礼貌说明无法回答。"""


def build_teacher_snapshot(db, teacher_id):
    """构建教师本人可见的数据快照，供教师端问答使用。"""
    teacher = db.get(Teacher, teacher_id)
    record = db.get(TeacherProfile, teacher_id)
    profile = effective_profile(record.payload if record else {})
    plans = db.query(AcademicPlan).order_by(AcademicPlan.id.desc()).all()

    open_plans = []
    drafts = []
    recommendations = []
    for plan in plans:
        tasks = [task_dict(db, t) for t in db.query(TeachingTask).filter_by(plan_id=plan.id).order_by(TeachingTask.id)]
        tasks = [t for t in tasks if t.get('start_week')]
        if plan.state == 'open':
            open_plans.append({
                'id': plan.id, 'name': plan.name,
                'tasks': [{'id': t['id'], 'name': t['name'], 'group': t.get('group'),
                           'direction': t.get('direction'), 'tags': t.get('tags') or []} for t in tasks],
            })
            from app.services import course_recommendation
            rec = course_recommendation.recommend_for_teacher(db, plan, teacher_id, 3)
            recommendations.append({'plan': plan.name,
                                    'courses': [{'name': r['name'], 'reason': r['reason']} for r in rec['recommendations']]})
        draft = db.query(PreferenceDraft).filter_by(plan_id=plan.id, teacher_id=teacher_id).first()
        if draft:
            names = [t['name'] for t in tasks if t['id'] in (draft.task_ids or [])]
            drafts.append({'plan': plan.name, 'selected': names})

    return {
        'teacher': {'name': teacher.name if teacher else '', 'direction': profile.get('direction'),
                    'tags': profile.get('tags'), 'skilled_courses': profile.get('skilled_courses')},
        'open_plans': open_plans,
        'recommendations': recommendations,
        'drafts': drafts,
    }


def answer_teacher_question(db, teacher_id, question):
    """回答教师端问题；失败回退简短规则回答。"""
    snapshot = build_teacher_snapshot(db, teacher_id)
    config = resolve_config(db)
    if db is not None:
        db.rollback()
    if not config or not config.get('api_key'):
        return {'answer': _teacher_rule_answer(snapshot, question), 'source': 'rules',
                'snapshot': snapshot, 'reason': '未配置 AI 服务'}

    user_text = ('教师数据：\n' + json.dumps(snapshot, ensure_ascii=False) + '\n\n问题：' + question)
    try:
        result = call_llm(config, TEACHER_SYSTEM_PROMPT, user_text, max_tokens=600)
        answer = result.get('text', '').strip()
        if not answer:
            raise ValueError('AI 未返回内容')
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        return {'answer': _teacher_rule_answer(snapshot, question), 'source': 'rules',
                'snapshot': snapshot, 'reason': f'{exc}，已回退规则回答'}
    return {'answer': answer, 'source': 'llm', 'provider': config.get('provider'),
            'model': result.get('model'), 'snapshot': snapshot}


def _teacher_rule_answer(snapshot, question):
    q = question.strip()
    if '推荐' in q or '选什么' in q or '选哪' in q:
        recs = snapshot.get('recommendations') or []
        if not recs:
            return '当前没有开放选课周期，暂无推荐。'
        courses = '、'.join(c['name'] for c in recs[0].get('courses', [])) or '暂无'
        return f"建议优先考虑：{courses}。"
    if '草稿' in q or '选了几' in q or '已选' in q:
        drafts = snapshot.get('drafts') or []
        if not drafts:
            return '当前还没有已选课程。'
        names = '、'.join(drafts[0].get('selected', [])) or '无'
        return f"你已选：{names}。"
    profile = snapshot.get('teacher') or {}
    return f"你的画像：方向「{profile.get('direction') or '未填写'}」，领域「{'、'.join(profile.get('tags') or []) or '未填写'}」。"

