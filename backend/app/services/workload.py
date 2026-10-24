"""管理员确认授课安排后的教师个人准确工作量。"""
import re

from app.models.planning import TeacherWorkloadEstimate
from app.services.stage_planning import occurrences


def base_factor(student_count) -> float:
    """25 人为基数 1，每增加 1 人增加 0.02；不足 25 人仍按 1。"""
    try:
        students = int(student_count or 0)
    except (TypeError, ValueError):
        students = 0
    return round(1 + 0.02 * max(0, students - 25), 4)


def supervision_kind(task) -> str | None:
    """识别毕业设计/毕业论文；名称同时含两者时需教师选择类型。"""
    name = re.sub(r'\s+', '', str(
        (task.get('source') or {}).get('course_metadata', {}).get('name')
        or task.get('name') or ''))
    if '毕业' in name and '设计' in name and '论文' in name:
        return 'ambiguous'
    if '毕业设计' in name:
        return 'design'
    if '毕业论文' in name:
        return 'thesis'
    return None


def actual_task_hours(task, plan, db=None) -> int:
    """实际授课课时：优先按周内节次统计；无节次时用培养方案周课时与尾周课时还原。"""
    if task.get('slots'):
        return len(list(occurrences(task, plan, db)))
    metadata = (task.get('source') or {}).get('course_metadata') or {}
    try:
        required = int(task.get('required_hours') or 0)
    except (TypeError, ValueError):
        required = 0
    tail_weeks = int(task.get('tail_weeks') or 0)
    tail_hours = metadata.get('tail_hours')
    weekly_hours = metadata.get('weekly_hours')
    weeks = metadata.get('teaching_weeks')
    if tail_weeks > 0 and isinstance(tail_hours, (int, float)) and isinstance(weekly_hours, (int, float)):
        try:
            # 以管理员实际设置的周段为准，方案的“上课周数”仅作兜底。
            span = int(task['end_week']) - int(task['start_week']) + 1
        except (KeyError, TypeError, ValueError):
            try:
                span = int(weeks) if weeks is not None else 0
            except (TypeError, ValueError):
                span = 0
        if span > 0:
            normal_weeks = max(0, span - tail_weeks)
            return int(normal_weeks * weekly_hours + tail_weeks * tail_hours)
    return required


def _estimate(db, plan, teacher_id, task_id):
    row = db.query(TeacherWorkloadEstimate).filter_by(
        plan_id=plan.id, teacher_id=teacher_id, task_id=task_id).first()
    return (row.payload if row else {}), (row.revision if row else 0)


def _assigned_weeks(db, plan, task, teacher_ids):
    rows = db.query(TeacherWorkloadEstimate).filter(
        TeacherWorkloadEstimate.plan_id == plan.id,
        TeacherWorkloadEstimate.task_id == task['id'],
        TeacherWorkloadEstimate.teacher_id.in_(teacher_ids))
    result = {}
    for row in rows:
        weeks = row.payload.get('weeks')
        if isinstance(weeks, (int, float)) and weeks > 0:
            result[row.teacher_id] = float(weeks)
    return result


def compute_teacher_workload(db, plan, teacher_id, tasks):
    """只统计管理员已审核锁定、且包含当前教师的任务。"""
    rows = []
    for task in tasks:
        assigned = list(task.get('teacher_ids') or [])
        if teacher_id not in assigned or not task.get('locked'):
            continue
        payload, revision = _estimate(db, plan, teacher_id, task['id'])
        student_count = int(task.get('actual_student_count') or task.get('student_count') or 0)
        base = base_factor(student_count)
        kind = supervision_kind(task)
        row = {
            'task_id': task['id'], 'name': task['name'], 'group': task.get('group', ''),
            'student_count': student_count, 'base': base,
            'course_hours': None, 'weeks': None, 'allocation': '',
            'workload': None, 'status': 'pending', 'note': '', 'formula': '',
            'kind': kind or ('shared' if len(assigned) > 1 else 'ordinary'),
            'estimate': {**payload, 'revision': revision},
        }
        if kind in {'design', 'thesis', 'ambiguous'}:
            effective = payload.get('guidance_kind') if kind == 'ambiguous' else kind
            if effective not in {'design', 'thesis'}:
                row['note'] = '待教师选择毕业设计或毕业论文'
            else:
                students = payload.get('guidance_students')
                if not isinstance(students, (int, float)) or students < 0:
                    row['note'] = '待教师填写本人指导人数'
                else:
                    rate = 12 if effective == 'design' else 8
                    row.update(kind=effective, guidance_students=students,
                               workload=round(students * rate, 2), status='confirmed',
                               formula=f'{students:g} 生 × {rate} 课时/生')
        elif student_count <= 0:
            # 实际选课人数在排课后由学生选课结果回填，未回填前不做人数系数计算。
            row['note'] = '待学生选课结束后统计实际授课人数'
        else:
            hours = actual_task_hours(task, plan, db)
            row['course_hours'] = hours
            if len(assigned) <= 1:
                row.update(weeks=None, allocation='全部',
                           workload=round(hours * base, 2), status='confirmed',
                           formula=f'{hours} 课时 × 基数 {base:g}')
            else:
                weeks = _assigned_weeks(db, plan, task, assigned)
                mine = weeks.get(teacher_id)
                expected = len(set(assigned))
                if not mine or len(weeks) < expected:
                    row['note'] = '待补充全部授课教师的本人授课周数后分配课时'
                else:
                    total_weeks = sum(weeks.values())
                    share = hours * mine / total_weeks
                    row.update(weeks=mine, allocation=f'{mine:g}/{total_weeks:g}',
                               workload=round(share * base, 2), status='confirmed',
                               formula=f'{hours} 课时 × {mine:g}/{total_weeks:g} 周 × 基数 {base:g}')
        rows.append(row)
    total = round(sum(row['workload'] or 0 for row in rows if row['status'] == 'confirmed'), 2)
    return {'plan_id': plan.id, 'plan_name': plan.name, 'plan_state': plan.state,
            'confirmed': bool(rows), 'rows': rows, 'total': total,
            'pending': sum(1 for row in rows if row['status'] != 'confirmed')}
