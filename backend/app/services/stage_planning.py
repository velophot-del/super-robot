from collections import defaultdict
from datetime import timedelta
from fastapi import HTTPException
from app.models.planning import AcademicPlan, TeachingTask, PeriodSlot, TeachingAssignment
from app.models.classroom import Classroom
from app.services.cohort_calendar import cohort_weeks, cohort_start_date, cohort_exam_weeks
from app.services.plan_versions import superseded_plan_ids


def task_dict(db, task):
    assignment = db.get(TeachingAssignment, task.id)
    room = db.get(Classroom, task.payload['room_id']) if task.payload.get('room_id') else None
    return {**task.payload, 'id': task.id, 'plan_id': task.plan_id,
            'slots': [{'day': s.day, 'start': s.start, 'count': s.count, 'phase': s.phase}
                      for s in db.query(PeriodSlot).filter_by(task_id=task.id).order_by(PeriodSlot.day)],
            'teacher_ids': assignment.teacher_ids if assignment else [],
            'locked': bool(assignment and assignment.locked),'room_name':room.name if room else None,
            'room_address':' · '.join(str(v) for v in [room.building, f'{room.floor}层' if room.floor is not None else None, room.name] if v) if room else None,
            # 实际选课人数在排课完成、学生选课结束后回填；未回填时为 0。
            'actual_student_count':task_student_count(task.payload)}


def task_student_count(task):
    try:
        return max(0, int(task.get('student_count') or 0))
    except (TypeError, ValueError):
        return 0


def validate_student_limit(db, task):
    """实际人数已回填时才校验上限；任务设置阶段不预设人数。"""
    limit=task.get('max_students')
    if limit is not None and task_student_count(task)>limit:
        raise HTTPException(409,f"{task['name']}的实际选课人数超过课程人数上限，请调整上限或教学组")


def occurrences(task, plan, db=None):
    start_date = cohort_start_date(db, plan, task.get('cohort')) if db is not None else plan.start_date
    for week in range(task['start_week'], task['end_week']+1):
        phase = 'tail' if task.get('tail_weeks', 0) and week > task['end_week']-task['tail_weeks'] else 'normal'
        for slot in task['slots']:
            if slot.get('phase', 'normal') != phase:
                continue
            date = start_date + timedelta(weeks=week-1, days=slot['day']-1)
            for period in range(slot['start'], slot['start']+slot['count']):
                yield week, date, period


def students_overlap(a, b):
    if a['group'] == b['group']:
        return True
    if a.get('student_ids') and b.get('student_ids'):
        return bool(set(a['student_ids']) & set(b['student_ids']))
    return bool(a.get('class_name') and a.get('class_name') == b.get('class_name'))


def validate_tasks(db, plan, tasks, check_slots=True):
    """校验任务可发布性。

    `check_slots=False` 仅用于不需要验证周内节次的预检；正式发布必须校验完整节次、
    计划学时、同日冲突和教室节次占用。
    """
    group_weeks = defaultdict(set)
    room_slots = set()
    prior = []
    for task in tasks:
        validate_student_limit(db,task)
        if not task.get('start_week') or not task.get('end_week'):
            raise HTTPException(409, f"{task['name']}尚未配置周段，不能发布")
        limit=cohort_weeks(db,plan,task.get('cohort'))
        if task['end_week'] > limit:
            raise HTTPException(409, f'课程周段超出该年级{limit}周授课周期')
        exam=cohort_exam_weeks(db,plan,task.get('cohort'),task.get('group'))
        blocked=sorted(exam & set(range(task['start_week'],task['end_week']+1)))
        if blocked:
            raise HTTPException(409, f"{task['name']}进入考试周（第{'、'.join(map(str,blocked))}周）")
        actual = list(occurrences(task, plan, db)) if check_slots else []
        if check_slots:
            if not task.get('slots'):
                raise HTTPException(409, f"{task['name']}尚未配置周内节次，不能发布")
            if len(actual) != task['required_hours']:
                raise HTTPException(409, f"{task['name']}安排{len(actual)}节，计划{task['required_hours']}节，学时不齐")
            own_days = {d for _,d,_ in actual}
            student_keys = ['student:'+s for s in task.get('student_ids',[])] or ['group:'+(task.get('class_name') or task['group'])]
            for week, _, _ in actual:
                for student_key in student_keys: group_weeks[(student_key, week)].add(task['code'])
            for other, other_days in prior:
                if students_overlap(task, other) and task['code'] != other['code'] and own_days & other_days:
                    raise HTTPException(409, '同日同一教学组只能安排1门专业课，剩余节次为该课程保留')
            prior.append((task, own_days))
            if any(len(courses) > 2 for courses in group_weeks.values()):
                raise HTTPException(409, '同一教学组每周最多2门专业课')
        if task.get('room_id'):
            room = db.get(Classroom, task['room_id'])
            required_capacity = task.get('max_students') or task.get('student_count') or 0
            if not room or not room.is_available or (required_capacity and room.capacity < required_capacity):
                raise HTTPException(409, '地点停用、不存在或容量不足')
            if task.get('room_type') and task['room_type'] != room.room_type:
                raise HTTPException(409, '地点类型不符合课程要求')
            if check_slots:
                for _,date,period in actual:
                    key = (room.id, date, period)
                    if key in room_slots:
                        raise HTTPException(409, '地点在实际日期节次冲突')
                    room_slots.add(key)
    if not check_slots:
        return
    published_tasks = []
    # Published plans reserve both rooms and student groups on actual dates.
    superseded = superseded_plan_ids(db)
    published_rows = [(other_plan, other)
                      for other_plan in db.query(AcademicPlan).filter(AcademicPlan.state == 'published', AcademicPlan.id != plan.id)
                      if other_plan.id not in superseded and other_plan.id != (plan.settings or {}).get('supersedes_plan_id')
                      for other in db.query(TeachingTask).filter_by(plan_id=other_plan.id)]
    for other_plan, other in published_rows:
        data = task_dict(db, other)
        if not data.get('start_week'):continue
        published_tasks.append((data,list(occurrences(data,other_plan,db))))
        for _,date,period in occurrences(data, other_plan,db):
            if (data.get('room_id'), date, period) in room_slots:
                raise HTTPException(409, '地点与其他已发布计划冲突')

    for task in tasks:
        days={d for _,d,_ in occurrences(task,plan,db)}
        courses_by_week=defaultdict(set)
        student_keys=task.get('student_ids') or [task.get('class_name') or task['group']]
        for data,slots in published_tasks:
            if students_overlap(task,data) and data['code']!=task['code'] and days & {d for _,d,_ in slots}:
                raise HTTPException(409,'教学组与其他已发布计划同日安排了不同课程')
        for data,slots in [(t,list(occurrences(t,plan,db))) for t in tasks]+published_tasks:
            if not students_overlap(task,data):continue
            keys=set(student_keys)&set(data['student_ids']) if task.get('student_ids') and data.get('student_ids') else student_keys
            for _,day,_ in slots:
                for key in keys:courses_by_week[(key,day-timedelta(days=day.weekday()))].add(data['code'])
        if any(len(courses_by_week[(key,d-timedelta(days=d.weekday()))])>2 for d in days for key in student_keys):
            raise HTTPException(409,'教学组合并已发布计划后每周超过2门专业课')


def capacity(db, plan, task, teacher_id, profile, chosen):
    weekly = defaultdict(int)
    daily = defaultdict(int)
    occupied = set()
    course_codes = set()
    candidate_start = cohort_start_date(db, plan, task.get('cohort'))
    candidate_end = candidate_start + timedelta(weeks=cohort_weeks(db, plan, task.get('cohort')))
    for other, other_plan in chosen:
        other_occurrences=[entry for entry in occurrences(other, other_plan,db)
                           if candidate_start <= entry[1] < candidate_end]
        if other_occurrences:
            course_codes.add(other['code'])
        for _,date,period in other_occurrences:
            occupied.add((date, period))
            relative_week = (date-candidate_start).days//7+1
            weekly[relative_week] += 1
            daily[date] += 1
    candidate_slots = list(occurrences(task, plan, db))
    reasons = []
    for week,date,period in candidate_slots:
        if (date,period) in occupied:
            reasons.append('教师实际授课节次冲突')
        weekly[week] += 1; daily[date] += 1
    if any(h > 8 for h in daily.values()): reasons.append('教师单日超过8节')
    for week in {w for w,_,_ in candidate_slots}:
        if weekly[week] + profile.get('external_hours', {}).get(str(week), 0) > profile.get('weekly_limit', 20):
            reasons.append(f'第{week}周系统内与外部课时合计超出上限')
    if len(course_codes | {task['code']}) > profile.get('course_limit', 3):
        reasons.append('学期不同课程数超过上限')
    return sorted(set(reasons)), weekly
