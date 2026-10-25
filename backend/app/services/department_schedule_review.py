"""Scope and immutable event projections for department schedule review."""
import hashlib
import json

from fastapi import HTTPException

from app.models.class_info import ClassInfo
from app.models.planning import (AcademicDirection, AcademicPlan, AcademicProgram,
                                 PlanningEvent, TeachingTask)
from app.models.teacher import Teacher
from app.services import department_review
from app.services.authorization import can
from app.services.stage_planning import task_dict


PROPOSAL_ACTION = 'department_schedule_proposal'
SUBMIT_ACTION = 'department_schedule_submit'
DECISION_ACTION = 'department_schedule_decision'


def reviewer_scope(db, user):
    if can(user, 'admin'):
        return None
    if not any(g.get('capability') == 'lead' and g.get('scope') == 'dept'
               for g in getattr(user, 'grants', [])):
        raise HTTPException(403, '没有教研室课程审核权限')
    teacher = db.get(Teacher, getattr(user, 'teacher_id', None))
    if not teacher or not teacher.offering_unit_id or not (teacher.review_major or '').strip():
        raise HTTPException(403, '请由管理员配置所属教研室和授权专业')
    program = db.query(AcademicProgram).filter_by(name=teacher.review_major.strip(), is_active=True).first()
    if not program:
        raise HTTPException(403, '授权专业未关联有效专业目录')
    linked = db.query(AcademicDirection.id).filter_by(
        program_id=program.id, offering_unit_id=teacher.offering_unit_id).first()
    if not linked:
        raise HTTPException(403, '授权专业未关联当前教研室')
    groups = {row.name for row in db.query(ClassInfo).filter(
        ClassInfo.is_active.is_(True),
        ((ClassInfo.program_id == program.id) |
         ((ClassInfo.program_id.is_(None)) & (ClassInfo.department == program.name))))}
    return {'teacher_id': teacher.id, 'unit_id': teacher.offering_unit_id,
            'major': program.name, 'groups': groups}


def task_fingerprint(db, task):
    from app.models.planning import PeriodSlot, TeachingAssignment
    assignment = db.get(TeachingAssignment, task.id)
    value = {
        'payload': task.payload,
        'slots': [{'day': row.day, 'start': row.start, 'count': row.count, 'phase': row.phase}
                  for row in db.query(PeriodSlot).filter_by(task_id=task.id).order_by(PeriodSlot.id)],
        'teacher_ids': assignment.teacher_ids if assignment else [],
    }
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def event_state(db, plan_ids):
    if not plan_ids:
        return {}
    rows = db.query(PlanningEvent).filter(
        PlanningEvent.plan_id.in_(plan_ids),
        PlanningEvent.action.in_([PROPOSAL_ACTION, SUBMIT_ACTION, DECISION_ACTION])
    ).order_by(PlanningEvent.id).all()
    state = {}
    for row in rows:
        payload = row.payload
        task_id = payload.get('task_id')
        if not task_id:
            continue
        current = state.setdefault((row.plan_id, task_id), {})
        if row.action == PROPOSAL_ACTION:
            current.update({'proposal_id': row.id, 'proposal': payload,
                            'status': 'draft', 'decision_reason': ''})
        elif row.action == SUBMIT_ACTION and current.get('proposal_id') == payload.get('proposal_id'):
            current.update({'status': 'submitted', 'submission_id': row.id})
        elif row.action == DECISION_ACTION and current.get('proposal_id') == payload.get('proposal_id'):
            current.update({'status': payload.get('status'), 'decision_reason': payload.get('reason', ''),
                            'applied_fingerprint': payload.get('applied_fingerprint')})
    return state


def plans_for_cycle(db, anchor):
    from app.api.planning import plan_info
    from app.services.academic_scope import plan_term
    anchor_info = plan_info(anchor, db)
    return [plan for plan in db.query(AcademicPlan).order_by(AcademicPlan.id)
            if plan.state in {'open', 'matched'}
            and plan_info(plan, db)['academic_year'] == anchor_info['academic_year']
            and plan_term(plan) == plan_term(anchor)]


def visible_plans_and_tasks(db, user, anchor_plan_id):
    from app.api.planning import get_plan, plan_info, latest_submissions, tasks_for
    from app.services.academic_scope import plan_term

    scope = reviewer_scope(db, user)
    anchor = get_plan(db, anchor_plan_id)
    if anchor.state not in {'open', 'matched'}:
        raise HTTPException(409, '仅开放或匹配中的周期可进行教研室课程审核')
    plans = plans_for_cycle(db, anchor)
    scoped_groups = scope['groups'] if scope else None
    events = event_state(db, [plan.id for plan in plans])
    all_teachers = {teacher.id: teacher.name for teacher in db.query(Teacher)}
    result = []
    for plan in plans:
        tasks = tasks_for(db, plan)
        if scoped_groups is not None:
            tasks = [item for item in tasks if item.get('group') in scoped_groups]
        submissions = latest_submissions(db, plan.id)
        submitted_task_ids = {task_id for submission in submissions.values()
                              for task_id in submission.task_ids}
        rows = []
        for item in tasks:
            model = db.get(TeachingTask, item['id'])
            meta = ((item.get('source') or {}).get('course_metadata') or {})
            course_unit = meta.get('offering_unit_id', item.get('offering_unit_id'))
            applicants = []
            for teacher_id, submission in submissions.items():
                teacher = db.get(Teacher, teacher_id)
                if not teacher or not department_review.may_review(db, user, teacher):
                    continue
                selected = item['id'] in submission.task_ids
                review_status = (department_review.status(db, plan, submission, item['id'])
                                 if selected else 'not_selected')
                applicants.append({'submission_id': submission.id, 'teacher_id': teacher_id,
                    'teacher_name': teacher.name, 'selected': selected,
                    'review_status': review_status,
                    'selected_task_ids': list(submission.task_ids),
                    'selected_course_names': [task['name'] for task in tasks
                                              if task['id'] in submission.task_ids]})
            schedule = events.get((plan.id, item['id']), {})
            fingerprint = task_fingerprint(db, model)
            current_status = schedule.get('status', 'pending')
            proposal = schedule.get('proposal', {}).get('proposal')
            expected_fingerprint = (schedule.get('applied_fingerprint') if current_status == 'approved'
                                    else schedule['proposal'].get('base_fingerprint')) if schedule else None
            if schedule and expected_fingerprint != fingerprint:
                current_status = 'stale'
            can_edit = scope is None or course_unit is None or course_unit == scope['unit_id']
            rows.append({**item, 'plan_id': plan.id, 'plan_name': plan.name,
                'plan_state': plan.state, 'plan_revision': plan.revision,
                'teacher_names': [all_teachers.get(tid, f'教师{tid}')
                                  for tid in item.get('teacher_ids', [])],
                'applicants': sorted(applicants, key=lambda value: value['teacher_name']),
                'proposal_id': schedule.get('proposal_id'), 'proposal': proposal,
                'proposal_teacher_names': [all_teachers.get(tid, f'教师{tid}')
                                           for tid in (proposal or {}).get('teacher_ids', [])],
                'department_schedule_status': current_status,
                'department_schedule_reason': schedule.get('decision_reason', ''),
                'base_fingerprint': fingerprint,
                'has_applications': item['id'] in submitted_task_ids,
                'can_direct_assign': bool(
                    scope is None or (can_edit and department_review.enabled(plan)
                                      and item['id'] not in submitted_task_ids)),
                'can_edit_department_schedule': can_edit,
                })
        result.append({**plan_info(plan, db), 'tasks': rows})
    return result


def require_task_scope(db, user, plan, task):
    if plan.state not in {'open', 'matched'}:
        raise HTTPException(409, '仅开放或匹配中的周期可进行教研室课程审核')
    scope = reviewer_scope(db, user)
    if scope is None:
        return scope
    details = task_dict(db, task)
    if details.get('group') not in scope['groups']:
        raise HTTPException(403, '该课程不在本教研室授权专业班级范围')
    meta = ((details.get('source') or {}).get('course_metadata') or {})
    course_unit = meta.get('offering_unit_id', details.get('offering_unit_id'))
    if course_unit is not None and course_unit != scope['unit_id']:
        raise HTTPException(403, '该课程由其他教研室负责调剂')
    return scope


def latest_task_state(db, plan_id, task_id):
    return event_state(db, [plan_id]).get((plan_id, task_id), {})


def latest_manual_event(db, task):
    """Latest immutable manual allocation for a task, used to protect administrator decisions."""
    rows = db.query(PlanningEvent).filter_by(
        plan_id=task.plan_id, action='manual_teacher_assignment').order_by(PlanningEvent.id.desc())
    return next((row for row in rows if row.payload.get('task_id') == task.id), None)


def validate_proposal(db, user, plan, task, proposal, require_approval=False):
    from app.api.planning import assigned_tasks, capacity, latest_submissions, profile_for

    current = task_dict(db, task)
    teacher_ids = proposal.get('teacher_ids') or []
    if len(teacher_ids) != current['teacher_count']:
        raise HTTPException(422, f"教师建议人数须为{current['teacher_count']}人")
    scope = reviewer_scope(db, user)
    submissions = latest_submissions(db, plan.id)
    claimed = any(task.id in submission.task_ids for submission in submissions.values())
    own_submission = submissions.get(getattr(user, 'teacher_id', None))
    if own_submission and task.id in own_submission.task_ids:
        raise HTTPException(403, '本人申报的课程须由其他审核人处理')
    if len(set(teacher_ids)) != len(teacher_ids):
        raise HTTPException(422, '教师不能重复选择')
    for teacher_id in teacher_ids:
        if require_approval and claimed:
            submission = submissions.get(teacher_id)
            if not submission or task.id not in submission.task_ids:
                raise HTTPException(409, '教师未申报本课程')
            department_review.require_approved(db, plan, submission, task.id)
        teacher = db.get(Teacher, teacher_id)
        if not teacher:
            raise HTTPException(404, '教师不存在')
        if scope and (teacher_id == scope['teacher_id'] or teacher.offering_unit_id != scope['unit_id']):
            raise HTTPException(403, '只能建议本室其他教师，且本人申请须回避')
        if not scope and teacher_id == getattr(user, 'teacher_id', None):
            raise HTTPException(403, '本人申请须回避')
        reasons, _ = capacity(db, plan, current, teacher_id, profile_for(db, teacher_id),
                              assigned_tasks(db, plan, teacher_id, task.id))
        if reasons:
            raise HTTPException(409, '；'.join(reasons))


def manual_teacher_ids(db, task):
    """Only an immutable administrator allocation event replaces submission approval."""
    from app.models.planning import TeachingAssignment
    assignment = db.get(TeachingAssignment, task.id)
    if not assignment or not assignment.locked:
        return set()
    rows = db.query(PlanningEvent).filter_by(plan_id=task.plan_id,
        action='manual_teacher_assignment').order_by(PlanningEvent.id.desc())
    record = next((row.payload for row in rows if row.payload.get('task_id') == task.id), {})
    if record.get('source') == 'department_confirmation':
        from app.api.planning import latest_submissions
        if any(task.id in submission.task_ids
               for submission in latest_submissions(db, task.plan_id).values()):
            return set()
    if (record.get('match_id') != assignment.match_id or record.get('teacher_ids') != assignment.teacher_ids
            or record.get('task_payload') != department_review.task_fingerprint(task.payload)):
        return set()
    return set(assignment.teacher_ids)
