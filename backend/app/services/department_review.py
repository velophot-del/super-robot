"""Submission-specific department decisions; audit events remain append-only."""
from fastapi import HTTPException
from app.models.planning import PlanningEvent, TeachingTask
from app.models.teacher import Teacher
from app.services.authorization import can


def enabled(plan):
    return bool((plan.settings or {}).get('department_review'))


def task_fingerprint(payload):
    # Teacher approval is tied to the course and teaching group. Schedule
    # placement is revalidated against current capacity at matching/publication.
    return {k:v for k,v in payload.items()
            if k not in {'room_id', 'student_count', 'start_week', 'end_week', 'tail_weeks', 'slots'}}


def may_review(db, user, teacher):
    if not teacher or teacher.id == getattr(user, 'teacher_id', None):
        return False
    if can(user, 'admin'):
        return True
    reviewer = db.get(Teacher, getattr(user, 'teacher_id', None))
    return bool(reviewer and reviewer.offering_unit_id and
                reviewer.offering_unit_id == teacher.offering_unit_id and
                any(g['capability'] == 'lead' for g in getattr(user, 'grants', [])))


def decisions(db, plan_id):
    result = {}
    for row in db.query(PlanningEvent).filter_by(plan_id=plan_id, action='department_review').order_by(PlanningEvent.id):
        result[(row.payload['submission_id'], row.payload['task_id'])] = row.payload
    return result


def status(db, plan, submission, task_id, records=None):
    if not enabled(plan):
        return 'legacy'
    decision = (records if records is not None else decisions(db, plan.id)).get((submission.id, task_id))
    teacher = db.get(Teacher, submission.teacher_id)
    task = db.get(TeachingTask, task_id)
    if not decision or not teacher or not task:
        return 'pending'
    if decision.get('unit_id') != teacher.offering_unit_id or decision.get('task_payload') != task_fingerprint(task.payload):
        return 'pending'
    return decision['status']


def require_approved(db, plan, submission, task_id):
    if status(db, plan, submission, task_id) not in {'approved', 'legacy'}:
        raise HTTPException(409, '该教师本次课程申请尚未通过教研室初审')


def may_resubmit(db, plan, teacher_id):
    from app.models.planning import PreferenceSubmission
    if not enabled(plan) or plan.state not in {'open','matched'} or not teacher_id:return False
    latest=db.query(PreferenceSubmission).filter_by(plan_id=plan.id,teacher_id=teacher_id).order_by(PreferenceSubmission.id.desc()).first()
    return bool(latest and any(status(db,plan,latest,task_id)=='returned' for task_id in latest.task_ids))
