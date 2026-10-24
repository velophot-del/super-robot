"""Draft timetable course placement by curriculum order and hard week constraints."""
import json

from fastapi import HTTPException

from app.models.planning import AcademicPlan, TeachingTask
from app.services.academic_scope import is_global, plan_term
from app.services.course_catalog import course_catalog_scope, course_schedule_info
from app.services.cohort_calendar import cohort_start_dates
from app.services.cohort_calendar import cohort_weeks, cohort_exam_weeks


def _rule_order(rows):
    return sorted(rows, key=lambda row: (
        row['major'], row['cohort'], row['semester'], row.get('course_type') or '',
        row.get('code') or '', row['name'], row['group']))


def _ai_order(db, rows):
    ordered = _rule_order(rows)
    from app.services.ai_config import LLMError, call_llm, resolve_config
    config = resolve_config(db)
    db.rollback()
    if not config or not config.get('api_key'):
        return ordered, 'rules', None
    items = [{
        'key': f"{row['course_id']}:{row['group']}", 'course': row['name'],
        'major': row['major'], 'cohort': row['cohort'], 'semester': row['semester'],
        'course_type': row.get('course_type'), 'credits': row.get('credits'),
        'required_hours': row.get('required_hours'), 'teaching_weeks': row.get('teaching_weeks'),
        'notes': row.get('notes') or '',
    } for row in ordered]
    try:
        result = call_llm(config,
            '你是高校课程培养方案编排助手。只返回JSON：{"order":["课程键"]}。依据专业课程体系、培养学期和课程衔接给出课程先后顺序。只能使用输入中的key，完整且不重复；不生成周次或其他字段。',
            '请为以下课程安排甘特图周段优先顺序：\n' + json.dumps(items, ensure_ascii=False),
            max_tokens=3000, json_mode=True)
        payload = json.loads(result.get('text') or '')
        keys = payload.get('order') if isinstance(payload, dict) else None
        known = {item['key'] for item in items}
        if isinstance(keys, list) and len(keys) == len(known) and set(keys) == known:
            by_key = {f"{row['course_id']}:{row['group']}": row for row in ordered}
            return [by_key[key] for key in keys], 'llm', result.get('model')
    except (LLMError, ValueError, TypeError, AttributeError):
        pass
    return ordered, 'rules', None


def _course_rows(db, plan):
    settings = plan.settings or {}
    groups = settings.get('groups') or None
    start_dates = cohort_start_dates(db, plan)
    if is_global(plan):
        scope = course_catalog_scope(db, plan.start_date, plan_term(plan), groups,start_dates_by_cohort=start_dates)
    else:
        scope = course_catalog_scope(db, plan.start_date, plan_term(plan), groups,
            settings.get('major'), settings.get('cohort'), settings.get('semester'),start_dates_by_cohort=start_dates)
    rows = []
    for item in scope:
        group = item['class']
        for course in item['courses']:
            info = course_schedule_info(course)
            rows.append({'course_id': course.id, 'name': course.name, 'code': course.course_code,
                'group': group.name, 'major': group.department or course.department or '',
                'cohort': str(group.grade or '').removesuffix('级').removesuffix('届'),
                'semester': item['semester'], 'course_type': course.course_type,
                'course_nature': course.course_nature, 'credits': course.credits,
                'required_hours': info['total_hours'], 'teaching_weeks': info['teaching_weeks'],
                'weekly_hours': info['weekly_hours'], 'weekdays': info['weekdays'],
                'source_total_hours': course.total_hours, 'tail_hours': course.tail_hours,
                'notes': course.remarks or ''})
    return rows


def _new_task_payload(row, start_week):
    duration = int(row['teaching_weeks'])
    return {'name': row['name'], 'code': row['code'], 'credits': row['credits'],
        'required_hours': row['required_hours'], 'direction': '', 'tags': [],
        'group': row['group'], 'class_name': row['group'], 'student_ids': [],
        'major': row['major'], 'department': row['major'], 'cohort': row['cohort'],
        'program_semester': row['semester'], 'start_week': start_week,
        'end_week': start_week + duration - 1,
        'tail_weeks': 1 if row.get('tail_hours') and duration > 1 else 0,
        'teacher_count': 1, 'mode': 'single', 'student_count': 0,
        'room_id': None, 'room_type': '', 'profile_verified': False,
        'source': {'course_id': row['course_id'], 'major': row['major'], 'cohort': row['cohort'],
            'course_metadata': {'course_type': row['course_type'], 'course_nature': row['course_nature'],
                'semester': row['semester'], 'teaching_weeks': duration,
                'weekdays': row['weekdays'], 'weekly_hours': row['weekly_hours'],
                'tail_hours': row['tail_hours']}}}


def autofill_draft_timetable(db, plan_id, revision, user):
    plan = db.get(AcademicPlan, plan_id)
    if not plan:
        raise HTTPException(404, '周期不存在')
    if plan.state != 'draft':
        raise HTTPException(409, 'AI自动填充仅适用于新建周期草稿')
    if plan.revision != revision:
        raise HTTPException(409, '周期版本已变化，请刷新后重试')
    rows = _course_rows(db, plan)
    if not rows:
        raise HTTPException(409, '当前周期没有匹配年级、专业和培养学期的可排课程')
    order, source, model = _ai_order(db, rows)

    from app.api.planning import event, write, tasks_for
    from app.api.stage_designer import validate_spans
    with write(db):
        plan = db.get(AcademicPlan, plan_id)
        if plan.state != 'draft' or plan.revision != revision:
            raise HTTPException(409, '周期已变化或不再是草稿状态，请刷新后重试')
        existing = tasks_for(db, plan)
        by_key = {}
        placed_keys = set()
        occupancy = {}
        for task in existing:
            course_id = (task.get('source') or {}).get('course_id')
            key = (course_id, task['group']) if course_id else (task['code'], task['group'])
            by_key[key] = task
            if task.get('start_week') and task.get('end_week'):
                placed_keys.add(key)
                for week in range(task['start_week'], task['end_week'] + 1):
                    occupancy.setdefault((task['group'], week), set()).add(task['code'])

        placed = []
        unplaced = []
        updated = []
        duplicate_keys = set()
        grouped_names = {}
        for row in order:
            name_key = (row['group'], row['semester'], row['name'].strip().casefold())
            grouped_names.setdefault(name_key, []).append(row)
        for same_name_rows in grouped_names.values():
            if len(same_name_rows) > 1:
                duplicate_keys.update((row['course_id'], row['group']) for row in same_name_rows)
        for row in order:
            key = (row['course_id'], row['group'])
            existing_task = by_key.get(key) or by_key.get((row['code'], row['group']))
            if key in placed_keys or (existing_task and existing_task.get('start_week')):
                continue
            if key in duplicate_keys:
                unplaced.append({'course': row['name'], 'group': row['group'],
                    'reason': '同一班级同一培养学期存在重名课程，请管理员核对课程库后再排'})
                continue
            if not row.get('source_total_hours') or row['source_total_hours'] <= 0:
                unplaced.append({'course': row['name'], 'group': row['group'],
                    'reason': '课程库未提供有效教学学时，请补充后再排'})
                continue
            try:
                duration = int(row.get('teaching_weeks') or 0)
            except (TypeError, ValueError):
                duration = 0
            if duration < 1:
                unplaced.append({'course': row['name'], 'group': row['group'], 'reason': '课程库未提供有效授课周数'})
                continue
            grade_weeks = cohort_weeks(db, plan, row['cohort'])
            exam_weeks = cohort_exam_weeks(db, plan, row['cohort'], row['group'])
            start_week = None
            for start in range(1, grade_weeks - duration + 2):
                span = set(range(start, start + duration))
                if span & exam_weeks:
                    continue
                if any(row['code'] in occupancy.get((row['group'], week), set()) or
                       len(occupancy.get((row['group'], week), set()) | {row['code']}) > 2
                       for week in span):
                    continue
                start_week = start
                break
            if start_week is None:
                unplaced.append({'course': row['name'], 'group': row['group'],
                    'reason': '剩余周段不足（受考试周、周期长度或每周最多两门课程限制）'})
                continue
            payload = _new_task_payload(row, start_week)
            if existing_task:
                existing_task.payload = {**existing_task.payload, **payload}
                task_id = existing_task.id
            else:
                task = TeachingTask(plan_id=plan.id, payload=payload)
                db.add(task); db.flush()
                task_id = task.id
            for week in range(start_week, start_week + duration):
                occupancy.setdefault((row['group'], week), set()).add(row['code'])
            placed.append({'task_id': task_id, 'course': row['name'], 'code': row['code'],
                'group': row['group'], 'major': row['major'], 'cohort': row['cohort'],
                'semester': row['semester'], 'start_week': start_week,
                'end_week': start_week + duration - 1})
            updated.append(task_id)

        if updated:
            validate_spans(plan, tasks_for(db, plan), db)
            plan.revision += 1
        event(db, user, 'ai_course_autofill', {'source': source, 'model': model,
            'filled': len(placed), 'unplaced': len(unplaced), 'task_ids': updated}, plan.id)
    return {'success': True, 'filled': len(placed), 'total_candidates': len(rows),
        'source': source, 'model': model, 'revision': plan.revision,
        'placed': placed, 'unplaced': unplaced}
