"""教师先申报的阶段式计划工作流。所有决定来自事务内最新版本。"""
import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.teacher import Teacher
from app.models.classroom import Classroom
from app.models.planning import (AcademicPlan, TeachingTask, PeriodSlot, TeacherProfile,
    PreferenceDraft, PreferenceSubmission, MatchRun, TeachingAssignment, PlanningEvent, PublishedPlan, TeacherWorkloadEstimate,
    TeacherScheduleConfirmation,ScheduleChangeRequest,ScheduleChangeDecision,TeacherNotification,CohortCalendarRule)
from app.schemas.planning import PlanInput, TaskInput, TaskLimitsInput, RoomInput, ActualStudentsInput, MatchWeightsInput, ProfileInput, DraftInput, SubmitInput, AssignmentInput, ManualAssignmentInput, SelfProfileInput, WorkloadEstimateInput, ScheduleConfirmationInput, ScheduleChangeRequestInput, ScheduleChangeDecisionInput
from app.services.auth import require_user
from app.services.authorization import can, check
from app.services.stage_planning import task_dict, validate_tasks, validate_student_limit, capacity
from app.services.academic_scope import is_global, plan_term, program_semester, groups_for_cycle, groups_in_cycle
from app.services.cohort_calendar import cohort_weeks, cohort_exam_weeks, cohort_start_dates, calendar_rule_payload
from app.services.matching_weights import get_match_weights, weight_items, weights_total
from app.services.workload import compute_teacher_workload
from app.services.teacher_course_matching import score_candidate
from app.services.personal_profile import require_personal_profile,missing_profile_fields,effective_profile
from app.services.course_catalog import course_catalog_scope, course_schedule_info
from app.services.ai_explanation import generate_ai_advice
from app.services.ai_config import LLMError, call_llm, resolve_config

router = APIRouter(prefix='/api/planning', tags=['教师选课与阶段计划'])


@contextmanager
def write(db):
    db.rollback()
    if db.bind.dialect.name == 'sqlite':
        db.execute(text('BEGIN IMMEDIATE'))
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def event(db, user, action, payload, plan_id=None):
    db.add(PlanningEvent(plan_id=plan_id, actor=f"{'demo' if getattr(user, 'is_demo', False) else 'user'}:{user.id}",
                         action=action, payload=payload))


def get_plan(db, plan_id):
    plan = db.get(AcademicPlan, plan_id)
    if not plan: raise HTTPException(404, '周期不存在')
    return plan


def tasks_for(db, plan):
    rows = db.query(TeachingTask).filter_by(plan_id=plan.id).order_by(TeachingTask.id).all()
    tasks = [task_dict(db, task) for task in rows]
    if plan.state != 'published' and is_global(plan):
        eligible = set(groups_for_cycle(db, plan.start_date, plan_term(plan), cohort_start_dates(db, plan)))
        from app.models.class_info import ClassInfo
        known = {row.name for row in db.query(ClassInfo)}
        tasks = [task for task in tasks if task.get('group') in eligible or task.get('group') not in known]
    return tasks


def latest_submissions(db, plan_id):
    latest = {}
    for row in db.query(PreferenceSubmission).filter_by(plan_id=plan_id).order_by(PreferenceSubmission.id):
        latest[row.teacher_id] = row
    return latest


def teacher_access(user):
    teacher_id = getattr(user, 'teacher_id', None)
    if teacher_id is None: raise HTTPException(403, '账号未绑定教师')
    check(user, 'teaching', {'teacher_id': teacher_id})
    return teacher_id


def can_read(user):
    return any(g['capability'] in {'admin', 'review', 'publish', 'teaching', 'lead'} for g in getattr(user,'grants',[]))


def plan_info(plan, db=None):
    cohort_rules = {}
    if db is not None:
        from app.models.planning import CohortCalendarRule
        cohort_rules = {row.cohort: calendar_rule_payload(row) for row in db.query(CohortCalendarRule)}
    return {'id':plan.id, 'name':plan.name, 'start_date':plan.start_date.isoformat(),
            'weeks':plan.weeks, 'deadline':plan.deadline.isoformat()+'Z', 'state':plan.state,
            'revision':plan.revision, 'rule_confirmed':plan.rule_confirmed, **(plan.settings or {}),
            'cohort_calendar_rules':cohort_rules,
            'academic_year':f"{plan.start_date.year if plan.start_date.month>=8 else plan.start_date.year-1}—{plan.start_date.year+1 if plan.start_date.month>=8 else plan.start_date.year}",
            'academic_term':plan_term(plan), 'global_cycle':is_global(plan)}


def profile_for(db, teacher_id):
    p = db.get(TeacherProfile, teacher_id)
    return effective_profile(p.payload if p else ProfileInput().model_dump())


def assigned_tasks(db, plan, teacher_id, exclude=None):
    chosen=[]
    for assignment in db.query(TeachingAssignment):
        if assignment.task_id == exclude or teacher_id not in assignment.teacher_ids: continue
        task = db.get(TeachingTask, assignment.task_id); other = db.get(AcademicPlan, task.plan_id)
        supersedes = (plan.settings or {}).get('supersedes_plan_id')
        if other.id == plan.id or (other.id != supersedes and other.state == 'published'):
            chosen.append((task_dict(db,task),other))
    return chosen


@router.get('/plans')
def list_plans(user=Depends(require_user), db: Session=Depends(get_db)):
    if not can_read(user): raise HTTPException(403, '账号尚未授予工作职能')
    return [plan_info(p, db) for p in db.query(AcademicPlan).order_by(AcademicPlan.id.desc())
            if p.state != 'draft' or can(user,'admin')]


@router.post('/plans')
def create_plan(data: PlanInput, user=Depends(require_user), db: Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        deadline=data.deadline
        if deadline.tzinfo is None: deadline=deadline.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
        global_cycle=data.global_cycle or (not data.major and not data.cohort)
        settings={'opening_date':data.opening_date.isoformat() if data.opening_date else None,'groups':data.groups}
        if global_cycle:
            # 仅纳入标准八学期学制内的有效班级。
            settings.update({'global': True, 'term': data.term})
            calendar_dates={row.cohort:row.start_date for row in db.query(CohortCalendarRule)}
            settings['groups']=groups_for_cycle(db,data.start_date,data.term,calendar_dates)
        else:
            settings.update(major=data.major,cohort=data.cohort,semester=data.semester)
        plan=AcademicPlan(name=data.name,start_date=data.start_date,weeks=data.weeks,
                          deadline=deadline.astimezone(timezone.utc).replace(tzinfo=None),rule_confirmed=data.rule_confirmed,
                          settings=settings)
        db.add(plan); db.flush(); event(db,user,'create_plan',data.model_dump(mode='json'),plan.id)
        return plan_info(plan, db)


@router.post('/plans/{plan_id}/generate')
def generate_tasks_from_course_catalog(plan_id: int, user=Depends(require_user), db: Session=Depends(get_db)):
    """从课程管理的活动课程库按班级专业、年级和周期学期生成教学任务。"""
    check(user, 'admin')
    with write(db):
        plan = get_plan(db, plan_id)
        if plan.state != 'draft':
            raise HTTPException(409, '非草稿计划不能重新生成')
        settings = plan.settings or {}
        start_dates = cohort_start_dates(db, plan)
        if is_global(plan):
            scope = course_catalog_scope(db, plan.start_date, plan_term(plan), settings.get('groups') or None,start_dates_by_cohort=start_dates)
        else:
            scope = course_catalog_scope(db, plan.start_date, plan_term(plan), settings.get('groups') or None,
                settings.get('major'), settings.get('cohort'), settings.get('semester'),start_dates_by_cohort=start_dates)
        if not scope:
            raise HTTPException(409, '课程库中没有匹配本周期有效班级、专业、年级和上课学期的活动课程')

        existing = tasks_for(db, plan)
        keys = {(task['code'], task['group']) for task in existing}
        added = 0
        for item in scope:
            cls = item['class']
            semester = item['semester']
            for course in item['courses']:
                key = (course.course_code, cls.name)
                if key in keys:
                    continue
                info = course_schedule_info(course)
                from app.models.planning import AcademicDirection
                direction = db.get(AcademicDirection, course.direction_id) if course.direction_id else None
                payload = {
                    'name': course.name,
                    'code': course.course_code,
                    'credits': course.credits,
                    'required_hours': info['total_hours'],
                    'direction': direction.name if direction else '',
                    'tags': [],
                    'group': cls.name,
                    'class_name': cls.name,
                    'student_ids': [],
                    'major': cls.department or course.department or '',
                    'department': cls.department or course.department or '',
                    'cohort': cls.grade,
                    'program_semester': semester,
                    'start_week': None,
                    'end_week': None,
                    'tail_weeks': 0,
                    'teacher_count': 1,
                    'mode': 'single',
                    'student_count': 0,
                    'room_id': None,
                    'room_type': '',
                    'profile_verified': False,
                    'source': {
                        'course_id': course.id,
                        'major': course.department or cls.department or '',
                        'cohort': cls.grade,
                        'course_metadata': {
                            'course_type': course.course_type,
                            'course_nature': course.course_nature,
                            'semester': course.semester,
                            'program_id': course.program_id,
                            'direction_id': course.direction_id,
                            'offering_unit_id': course.offering_unit_id,
                            'teaching_weeks': info['teaching_weeks'],
                            'weekdays': info['weekdays'],
                            'weekly_hours': info['weekly_hours'],
                            'tail_hours': course.tail_hours,
                        },
                    },
                }
                db.add(TeachingTask(plan_id=plan.id, payload=payload))
                keys.add(key)
                added += 1
        if added:
            plan.revision += 1
        db.flush()
        event(db, user, 'generate_tasks_from_course_catalog', {'classes': len(scope), 'added': added}, plan.id)
        return {'task_count': len(existing) + added, 'added': added, 'needs_schedule': True,
                'classes': len(scope), 'source': 'course_catalog'}


@router.get('/plans/{plan_id}')
def get_state(plan_id: int, user=Depends(require_user), db: Session=Depends(get_db), review_only: bool = Query(False)):
    plan=get_plan(db,plan_id)
    if not can_read(user) or (plan.state=='draft' and not can(user,'admin')): raise HTTPException(403,'计划尚未开放')
    if review_only and not can(user,'admin') and not any(g['capability'] in {'review','lead'} for g in getattr(user,'grants',[])):
        raise HTTPException(403,'账号没有审核职能')
    snapshot=db.query(PublishedPlan).filter_by(plan_id=plan.id).order_by(PublishedPlan.id.desc()).first() if plan.state=='published' else None
    all_tasks=deepcopy(snapshot.payload['tasks']) if snapshot else tasks_for(db,plan)
    if not can(user,'admin'):all_tasks=[t for t in all_tasks if t.get('start_week') and t.get('end_week')]
    if review_only:
        tasks=[t for t in all_tasks if can(user,'admin') or can(user,'review',t)]
    else:
        tasks=[t for t in all_tasks if can(user,'admin') or can(user,'publish') or
               can(user,'teaching',{'teacher_id':getattr(user,'teacher_id',None)}) or can(user,'review',t)]
    names={t.id:t.name for t in db.query(Teacher)}
    for task in tasks:
        if not snapshot:task['teacher_names']=[names.get(t,'') for t in task['teacher_ids']]
    teacher_id=getattr(user,'teacher_id',None)
    draft=db.query(PreferenceDraft).filter_by(plan_id=plan.id,teacher_id=teacher_id).first() if teacher_id else None
    latest=latest_submissions(db,plan.id)
    applicants_by_task={}
    for applicant_id,submission in latest.items():
        for task_id in submission.task_ids:
            applicants_by_task.setdefault(task_id,[]).append(
                {'teacher_id':applicant_id,'teacher_name':names.get(applicant_id,'')})
    for task in tasks:
        if can(user,'admin') or can(user,'review',task):
            task['applicants']=sorted(applicants_by_task.get(task['id'],[]),key=lambda item:item['teacher_name'])
            task['applicant_count']=len(task['applicants'])
    submitted=latest.get(teacher_id)
    run=db.query(MatchRun).filter_by(plan_id=plan.id).order_by(MatchRun.id.desc()).first()
    candidates=[]
    if run:
        for c in run.payload['candidates']:
            task=next((t for t in tasks if t['id']==c['task_id']),None)
            if task is None:continue
            if (not review_only and c['teacher_id']==teacher_id) or can(user,'review',task):
                candidates.append({**c,'teacher_name':names.get(c['teacher_id'],'')})
    estimates={r.task_id:{**r.payload,'revision':r.revision} for r in db.query(TeacherWorkloadEstimate).filter_by(plan_id=plan.id,teacher_id=teacher_id)} if teacher_id else {}
    weights=get_match_weights(plan)
    info={**deepcopy(snapshot.payload['plan']),'state':'published'} if snapshot else plan_info(plan, db)
    if plan.state!='published' and is_global(plan):
        info['groups']=groups_in_cycle(db,plan)
    if any(g['capability']=='lead' for g in getattr(user,'grants',[])):
        info['groups']=sorted({task['group'] for task in tasks if task.get('group')})
    from app.models.class_info import ClassInfo
    visible_groups=set(info.get('groups') or [task['group'] for task in tasks])
    if snapshot:
        class_scopes=[{'name':task['group'],'grade':task.get('cohort'),'department':task.get('major') or task.get('department')} for task in tasks]
    else:
        class_scopes=[{'name':row.name,'grade':row.grade,'department':row.department} for row in db.query(ClassInfo).filter(ClassInfo.name.in_(visible_groups))]
    return {**info,'tasks':tasks,'class_scopes':class_scopes,'snapshot_id':snapshot.id if snapshot else None,'workload_estimates':estimates,
        'match_weights':weights,'match_weight_items':weight_items(weights),'match_weight_total':weights_total(weights),
        'draft':({'revision':draft.revision,'task_ids':draft.task_ids,'plan_revision':draft.plan_revision} if draft else {'revision':0,'task_ids':[],'plan_revision':plan.revision}) if not review_only else {'revision':0,'task_ids':[],'plan_revision':plan.revision},
        'submission':{'id':submitted.id,'task_ids':submitted.task_ids} if submitted and not review_only else None,
        'submission_count':len(latest) if can(user,'admin') or any(can(user,'review',t) for t in tasks) else None,
        'match':{'id':run.id,'maximum':run.payload.get('maximum',weights_total(weights)),'weights':run.payload.get('match_weights',weights),
            'ai':run.payload.get('ai'),
            'candidates':candidates,'suggestions':[
            s for s in run.payload['suggestions'] if any(t['id']==s['task_id'] and can(user,'review',t) for t in tasks)]} if run else None}


def _ai_context(db, plan, tasks):
    """把周期状态压缩为模型/规则分析需要的结构化上下文。"""
    teacher_names = {t.id: t.name for t in db.query(Teacher)}
    stats = {'total': len(tasks), 'placed': 0, 'with_slots': 0, 'with_room': 0, 'locked': 0}
    issues = []
    flagged = {}

    def add(task, category, message):
        issues.append({'task_id': task['id'], 'name': task['name'], 'group': task.get('group', ''),
                       'category': category, 'level': 'blocking', 'message': message})
        flagged[task['id']] = task

    for task in tasks:
        has_span = bool(task.get('start_week') and task.get('end_week'))
        has_slots = bool(task.get('slots'))
        has_room = bool(task.get('room_id'))
        assigned = list(task.get('teacher_ids') or [])
        locked = bool(task.get('locked') and len(assigned) == task.get('teacher_count'))
        stats['placed'] += int(has_span)
        stats['with_slots'] += int(has_slots)
        stats['with_room'] += int(has_room)
        stats['locked'] += int(locked)

        if not has_span:
            add(task, 'missing_weeks', '尚未安排教学周段')
        else:
            if task['end_week'] > plan.weeks:
                add(task, 'span_out_of_range', f"周段 W{task['start_week']}—W{task['end_week']} 超出周期 {plan.weeks} 周")
            limit = cohort_weeks(db, plan, task.get('cohort'))
            if task['end_week'] > limit:
                add(task, 'span_out_of_range', f"周段 W{task['start_week']}—W{task['end_week']} 超出该年级{limit}周授课周期")
            exam = cohort_exam_weeks(db, plan, task.get('cohort'), task.get('group'))
            blocked = sorted(exam & set(range(task['start_week'], task['end_week'] + 1)))
            if blocked:
                add(task, 'exam_week', f"周段进入考试周（第{'、'.join(map(str, blocked))}周）")
        if not has_slots:
            add(task, 'missing_slots', '尚未配置周内节次')
        if not has_room:
            add(task, 'missing_room', '尚未落实上课地点')
        if not locked:
            add(task, 'unassigned', '授课教师尚未审核锁定或人数与名额不符')
        elif has_span and has_slots:
            for tid in assigned:
                reasons, _ = capacity(db, plan, task, tid, profile_for(db, tid),
                                      assigned_tasks(db, plan, tid, task['id']))
                if reasons:
                    add(task, 'capacity', f"教师「{teacher_names.get(tid, tid)}」：{'；'.join(reasons)}")

    groups = (plan.settings or {}).get('groups') or sorted(
        {task.get('group') for task in tasks if task.get('group')})
    return {
        'plan': {'name': plan.name, 'state': plan.state, 'start_date': plan.start_date.isoformat(),
                 'weeks': plan.weeks, 'group_count': len(groups)},
        'stats': stats,
        'issues': issues,
        'tasks_with_issues': [
            {'id': task['id'], 'name': task['name'], 'group': task.get('group', ''),
             'cohort': task.get('cohort', ''), 'start_week': task.get('start_week'),
             'end_week': task.get('end_week'), 'slots': len(task.get('slots') or []),
             'room': task.get('room_name') or '',
             'teachers': [teacher_names.get(tid, str(tid)) for tid in (task.get('teacher_ids') or [])],
             'required_hours': task.get('required_hours')}
            for task in flagged.values()
        ],
    }


@router.post('/plans/{plan_id}/ai-review')
def ai_review(plan_id: int, user=Depends(require_user), db: Session = Depends(get_db)):
    """管理员按当前周期状态生成 AI 排课分析；未配置模型密钥时自动使用规则分析。"""
    check(user, 'admin')
    plan = get_plan(db, plan_id)
    plan_state = plan.state
    context = _ai_context(db, plan, tasks_for(db, plan))
    result = generate_ai_advice(context, db)
    event(db, user, 'ai_review', {'source': result.get('source'), 'model': result.get('model'),
                                  'issue_count': result.get('issue_count', 0)}, plan_id)
    db.commit()
    return {**result, 'plan_id': plan_id, 'plan_state': plan_state}


def own_profile_response(db,tid):
    teacher=db.get(Teacher,tid)
    if not teacher:raise HTTPException(404,'绑定的教师不存在')
    record=db.get(TeacherProfile,tid);payload=record.payload if record else {}
    own=payload.get('self_profile') or {'direction':payload.get('direction',''),'tags':payload.get('tags',[]),'skilled_courses':[]}
    own={**own,'participating_course_ids':own.get('participating_course_ids',[])}
    missing=missing_profile_fields(payload)
    return {'teacher':{'id':tid,'name':teacher.name,'teacher_code':teacher.teacher_code,'department':teacher.department,'title':teacher.title},
            'revision':record.revision if record else 0,'profile':own,'ready':not missing,'missing':missing}


@router.get('/self-profile')
def own_profile(user=Depends(require_user),db:Session=Depends(get_db)):
    tid=teacher_access(user)
    return own_profile_response(db,tid)


@router.get('/self-profile/directions')
def own_profile_directions(user=Depends(require_user),db:Session=Depends(get_db)):
    teacher_access(user)
    return ['视觉传达设计','包装设计','智能交互设计','数字艺术','时尚传播']


@router.get('/self-profile/courses')
def own_course_catalog(user=Depends(require_user),db:Session=Depends(get_db)):
    teacher_access(user)
    from app.models.course import Course
    names={task.payload['name'] for task in db.query(TeachingTask).join(AcademicPlan).filter(AcademicPlan.state!='draft')}
    names.update(course.name for course in db.query(Course).filter(Course.is_active.is_(True)))
    return sorted(names)[:2000]


@router.get('/self-profile/course-groups')
def own_course_groups(user=Depends(require_user),db:Session=Depends(get_db)):
    teacher_access(user)
    from app.services.course_library import professional_courses
    return [{'id':c.id,'name':c.name,'course_code':c.course_code,'department':c.department}
            for c in professional_courses(db)]


@router.put('/self-profile')
def save_own_profile(data:SelfProfileInput,user=Depends(require_user),db:Session=Depends(get_db)):
    tid=teacher_access(user)
    with write(db):
        if not db.get(Teacher,tid):raise HTTPException(404,'绑定的教师不存在')
        record=db.get(TeacherProfile,tid)
        if data.revision!=(record.revision if record else 0):raise HTTPException(409,'个人资料已有新版本，请刷新后重试')
        payload=dict(record.payload) if record else ProfileInput().model_dump()
        from app.services.course_library import professional_courses
        if 'participating_course_ids' in data.model_fields_set:
            available={c.id for c in professional_courses(db)}
            if any(cid not in available for cid in data.participating_course_ids):
                raise HTTPException(422,'参与课程组包含不存在或非专业课的课程，请刷新后重新选择')
        own=data.model_dump(exclude={'revision'})
        if 'participating_course_ids' not in data.model_fields_set:
            own['participating_course_ids']=(payload.get('self_profile') or {}).get('participating_course_ids',[])
        payload['self_profile']=own
        if record:record.payload=payload;record.revision+=1
        else:db.add(TeacherProfile(teacher_id=tid,payload=payload,revision=1))
        db.flush();event(db,user,'self_profile_update',{'teacher_id':tid,'fields':list(payload['self_profile'])})
        return own_profile_response(db,tid)


@router.get('/profiles')
def list_profiles(user=Depends(require_user), db: Session=Depends(get_db)):
    check(user,'admin')
    return [{'id':t.id,'name':t.name,**profile_for(db,t.id)} for t in db.query(Teacher).order_by(Teacher.id)]


@router.put('/profiles/{teacher_id}')
def update_profile(teacher_id: int, data: ProfileInput, user=Depends(require_user), db: Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        if not db.get(Teacher,teacher_id): raise HTTPException(404,'教师不存在')
        profile=db.get(TeacherProfile,teacher_id)
        if profile:
            own=profile.payload.get('self_profile')
            profile.payload={**data.model_dump(),**({'self_profile':own} if own else {})};profile.revision+=1
        else: db.add(TeacherProfile(teacher_id=teacher_id,payload=data.model_dump(),revision=1))
        event(db,user,'update_profile',{'teacher_id':teacher_id,**data.model_dump()})
        return {'success':True}


@router.post('/plans/{plan_id}/tasks')
def add_task(plan_id: int, data: TaskInput, user=Depends(require_user), db: Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state!='draft': raise HTTPException(409,'开放后的计划内容已锁定；请建立新修订')
        tasks=tasks_for(db,plan)
        if any(t.get('start_week') and t['code']==data.code and t['group']==data.group and not (t['end_week']<data.start_week or t['start_week']>data.end_week) for t in tasks):
            raise HTTPException(409,'同组同课程周段重复，请使用多人名额或不重叠的分段')
        payload=data.model_dump()
        from app.api.stage_designer import validate_spans
        validate_spans(plan,[*tasks,payload],db)
        validate_student_limit(db,payload)
        complete=[t for t in [*tasks,payload] if t.get('start_week') and t.get('slots')]
        if complete:validate_tasks(db,plan,complete)
        slots=payload.pop('slots'); task=TeachingTask(plan_id=plan.id,payload=payload); db.add(task);db.flush()
        db.add_all([PeriodSlot(task_id=task.id,**s) for s in slots]); db.flush()
        plan.revision+=1; event(db,user,'create_task',data.model_dump(),plan.id)
        return task_dict(db,task)


@router.put('/plans/{plan_id}/tasks/{task_id}')
def update_task(plan_id:int,task_id:int,data:TaskInput,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id);task=db.get(TeachingTask,task_id)
        if plan.state!='draft':raise HTTPException(409,'开放后内容只读，请建立新修订')
        if not task or task.plan_id!=plan.id:raise HTTPException(404,'任务不存在')
        payload=data.model_dump()
        # 局部编辑只覆盖显式提交的字段，其余字段（地点、人数、模式等）沿用原任务。
        for key,value in task.payload.items():
            if key not in data.model_fields_set:
                payload[key]=value
        if 'slots' not in data.model_fields_set:
            payload['slots']=[{'day':s.day,'start':s.start,'count':s.count,'phase':s.phase}
                              for s in db.query(PeriodSlot).filter_by(task_id=task.id).order_by(PeriodSlot.id)]
        if task.payload.get('source'):
            for key in ['code','name','credits','required_hours']:
                if payload[key]!=task.payload[key]:raise HTTPException(409,'课程来源字段不可在任务中覆盖，请在课程管理中修改课程信息')
            payload['source']=task.payload['source']
        from app.api.stage_designer import validate_spans
        all_others=[t for t in tasks_for(db,plan) if t['id']!=task_id]
        validate_spans(plan,[*all_others,payload],db)
        validate_student_limit(db,payload)
        others=[t for t in all_others if t.get('start_week') and t.get('slots')]
        complete=[t for t in [*others,payload] if t.get('slots')]
        if complete:validate_tasks(db,plan,complete)
        slots=payload.pop('slots');task.payload=payload
        if 'slots' in data.model_fields_set:
            db.query(PeriodSlot).filter_by(task_id=task.id).delete()
            db.add_all([PeriodSlot(task_id=task.id,**s) for s in slots])
        db.flush()
        plan.revision+=1;event(db,user,'edit_task',{'task_id':task_id,'data':{**payload,'slots':slots}},plan.id)
        return task_dict(db,task)


@router.put('/plans/{plan_id}/tasks/{task_id}/limits')
def set_task_limits(plan_id:int,task_id:int,data:TaskLimitsInput,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state!='draft' or plan.revision!=data.revision:
            raise HTTPException(409,'周期已锁定或版本已变化，请刷新后重试')
        task=db.get(TeachingTask,task_id)
        if not task or task.plan_id!=plan.id:raise HTTPException(404,'任务不存在')
        payload={**task.payload,'teacher_count':data.teacher_count,'max_students':data.max_students}
        validate_student_limit(db,payload)
        task.payload=payload;plan.revision+=1;db.flush()
        event(db,user,'set_task_limits',{'task_id':task_id,**data.model_dump()},plan.id)
        return {'revision':plan.revision,'task':task_dict(db,task)}


@router.put('/plans/{plan_id}/tasks/{task_id}/room')
def set_task_room(plan_id:int,task_id:int,data:RoomInput,user=Depends(require_user),db:Session=Depends(get_db)):
    """开放填报后单独设置或清除上课地点。

    地点不属于志愿匹配的输入，因此不递增 plan.revision，避免已提交意愿失效。
    """
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state not in {'open','matched'}:
            raise HTTPException(409,'仅开放填报或匹配阶段可以单独调整地点')
        task=db.get(TeachingTask,task_id)
        if not task or task.plan_id!=plan.id:raise HTTPException(404,'任务不存在')
        if not task.payload.get('start_week'):raise HTTPException(409,'任务尚未配置周段')

        if data.room_id is not None:
            room=db.get(Classroom,data.room_id)
            if not room:raise HTTPException(404,'地点不存在')
            if not room.is_available:raise HTTPException(409,'地点已停用')
            required_capacity=task.payload.get('max_students') or task.payload.get('student_count') or 0
            if required_capacity and room.capacity < required_capacity:raise HTTPException(409,'地点容量小于课程人数上限')
            if task.payload.get('room_type') and task.payload['room_type']!=room.room_type:
                raise HTTPException(409,'地点类型不符合课程要求')

        task.payload={**task.payload,'room_id':data.room_id}
        # SessionLocal 关闭了 autoflush，必须显式 flush 才能让校验读到新地点
        db.flush()
        complete=[t for t in tasks_for(db,plan) if t.get('start_week') and t.get('slots')]
        if complete:validate_tasks(db,plan,complete)
        event(db,user,'set_room',{'task_id':task_id,'room_id':data.room_id},plan.id)
        return task_dict(db,task)


@router.put('/plans/{plan_id}/tasks/{task_id}/actual-students')
def set_actual_students(plan_id:int,task_id:int,data:ActualStudentsInput,user=Depends(require_user),db:Session=Depends(get_db)):
    """排课完成、学生选课结束后回填实际选课人数，用于真实工作量计算。"""
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state not in {'matched','published'}:
            raise HTTPException(409,'排课完成并进入匹配/发布阶段后才能回填实际选课人数')
        task=db.get(TeachingTask,task_id)
        if not task or task.plan_id!=plan.id:raise HTTPException(404,'任务不存在')
        limit=task.payload.get('max_students')
        if limit is not None and data.student_count>limit:
            raise HTTPException(409,'实际选课人数超过课程人数上限，请先调整上限')
        room=db.get(Classroom,task.payload['room_id']) if task.payload.get('room_id') else None
        if room and room.capacity<data.student_count:raise HTTPException(409,'实际选课人数超过教室容量')
        task.payload={**task.payload,'student_count':data.student_count}
        db.flush();event(db,user,'set_actual_students',{'task_id':task_id,'student_count':data.student_count},plan.id)
        return task_dict(db,task)


@router.post('/plans/{plan_id}/open')
def open_plan(plan_id: int,user=Depends(require_user),db: Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id); tasks=[t for t in tasks_for(db,plan) if t.get('start_week')]
        if plan.state!='draft' or not tasks: raise HTTPException(409,'只有包含完整任务的草稿可以开放')
        if plan.deadline<=datetime.now(timezone.utc).replace(tzinfo=None): raise HTTPException(409,'申报截止时间已过')
        # 开放填报只确认阶段任务；精确节次、学时与地点在正式发布时校验。
        from app.api.stage_designer import validate_spans
        validate_spans(plan,tasks,db)
        for task in tasks:validate_student_limit(db,task)
        if any(not isinstance(t.get('required_hours'),int) or t['required_hours']<=0 for t in tasks):
            raise HTTPException(409,'请先核对课程计划学时')
        plan.state='open';event(db,user,'open',{},plan.id)
        return plan_info(plan, db)


def editable(plan):
    if plan.state!='open': raise HTTPException(409,'当前不处于选课填报阶段')
    if plan.deadline<=datetime.now(timezone.utc).replace(tzinfo=None): raise HTTPException(409,'填报已截止')


@router.put('/plans/{plan_id}/draft')
def save_draft(plan_id: int,data: DraftInput,user=Depends(require_user),db: Session=Depends(get_db)):
    tid=teacher_access(user)
    with write(db):
        require_personal_profile(db,tid)
        plan=get_plan(db,plan_id);editable(plan)
        if data.plan_revision!=plan.revision:raise HTTPException(409,'计划已变更，请重新核对')
        ids={t.id for t in db.query(TeachingTask).filter_by(plan_id=plan.id) if t.payload.get('start_week')}
        if len(set(data.task_ids))!=len(data.task_ids) or not set(data.task_ids)<=ids:raise HTTPException(422,'课程任务无效或重复')
        draft=db.query(PreferenceDraft).filter_by(plan_id=plan.id,teacher_id=tid).first()
        if data.revision!=(draft.revision if draft else 0):raise HTTPException(409,'草稿已有新版本，请刷新核对')
        if draft: draft.task_ids=data.task_ids;draft.plan_revision=plan.revision;draft.revision+=1
        else: draft=PreferenceDraft(plan_id=plan.id,teacher_id=tid,task_ids=data.task_ids,plan_revision=plan.revision,revision=1);db.add(draft)
        return {'revision':draft.revision,'task_ids':draft.task_ids,'plan_revision':plan.revision}


@router.put('/plans/{plan_id}/tasks/{task_id}/workload-estimate')
def save_workload_estimate(plan_id:int,task_id:int,data:WorkloadEstimateInput,user=Depends(require_user),db:Session=Depends(get_db)):
    tid=teacher_access(user)
    with write(db):
        require_personal_profile(db,tid)
        plan=get_plan(db,plan_id)
        task=db.get(TeachingTask,task_id)
        if not task or task.plan_id!=plan.id:raise HTTPException(404,'课程任务不存在')
        if plan.state=='open':
            editable(plan)
            draft=db.query(PreferenceDraft).filter_by(plan_id=plan.id,teacher_id=tid).first()
            if not draft or task_id not in draft.task_ids:raise HTTPException(409,'请先预选本课程再填写估算参数')
        elif plan.state=='matched':
            assignment=db.get(TeachingAssignment,task_id)
            if not assignment or not assignment.locked or tid not in assignment.teacher_ids:
                raise HTTPException(403,'仅管理员已确认授课的教师可填写工作量参数')
        else:
            raise HTTPException(409,'计划已发布，工作量参数已冻结')
        if data.weeks is not None and data.weeks>plan.weeks:raise HTTPException(422,'本人授课周数不能超过周期周数')
        record=db.query(TeacherWorkloadEstimate).filter_by(plan_id=plan.id,teacher_id=tid,task_id=task_id).first()
        if data.revision!=(record.revision if record else 0):raise HTTPException(409,'估算参数已有新版本，请刷新后核对')
        payload=data.model_dump(exclude={'revision'})
        if record:record.payload=payload;record.revision+=1
        else:
            record=TeacherWorkloadEstimate(plan_id=plan.id,teacher_id=tid,task_id=task_id,payload=payload,revision=1)
            db.add(record)
        db.flush()
        return {**record.payload,'revision':record.revision}


@router.post('/plans/{plan_id}/submit')
def submit(plan_id:int,data:SubmitInput,user=Depends(require_user),db:Session=Depends(get_db)):
    tid=teacher_access(user)
    with write(db):
        require_personal_profile(db,tid)
        plan=get_plan(db,plan_id);editable(plan)
        draft=db.query(PreferenceDraft).filter_by(plan_id=plan.id,teacher_id=tid).first()
        if not draft or draft.revision!=data.revision or draft.plan_revision!=plan.revision:raise HTTPException(409,'草稿或计划版本已变更')
        minimum=min(3,sum(bool(t.payload.get('start_week')) for t in db.query(TeachingTask).filter_by(plan_id=plan.id)))
        if len(draft.task_ids)<minimum:raise HTTPException(422,f'本周期至少选择{minimum}门课程（最多5门）')
        previous=latest_submissions(db,plan.id).get(tid)
        if previous and previous.draft_revision==draft.revision:return {'id':previous.id,'task_ids':previous.task_ids}
        row=PreferenceSubmission(plan_id=plan.id,teacher_id=tid,task_ids=list(draft.task_ids),plan_revision=plan.revision,draft_revision=draft.revision)
        db.add(row);db.flush();event(db,user,'submit',{'teacher_id':tid,'task_ids':draft.task_ids},plan.id)
        return {'id':row.id,'task_ids':row.task_ids}


@router.put('/plans/{plan_id}/match-weights')
def set_match_weights(plan_id:int,data:MatchWeightsInput,user=Depends(require_user),db:Session=Depends(get_db)):
    """管理员调整五项系统匹配权重；下一次匹配生效，不使已提交志愿失效。"""
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state=='published':raise HTTPException(409,'已发布周期的匹配权重已冻结')
        weights=data.model_dump()
        plan.settings={**(plan.settings or {}),'match_weights':weights}
        db.flush();event(db,user,'set_match_weights',weights,plan.id)
        return {'match_weights':weights,'match_weight_items':weight_items(weights),
                'match_weight_total':weights_total(weights)}


def _match_snapshot(db, plan):
    """构建匹配所需的只读快照，并记录用于并发校验的指纹。"""
    tasks = [t for t in tasks_for(db, plan) if t.get('start_week')]
    latest = latest_submissions(db, plan.id)
    candidates = []
    profiles = {}
    for tid, submission in latest.items():
        if submission.plan_revision != plan.revision:
            raise HTTPException(409, '存在过时申报，请先处理')
        profile = profile_for(db, tid)
        p = db.get(TeacherProfile, tid)
        profiles[str(tid)] = p.revision if p else 0
        for task_id in submission.task_ids:
            task = next((t for t in tasks if t['id'] == task_id), None)
            if task is not None:
                candidates.append(score_candidate(db, plan, task, tid, profile, assigned_tasks(db, plan, tid, task_id)))
    weights = get_match_weights(plan)
    fingerprint = (plan.revision, plan.state,
                   tuple(sorted((str(t), r.id) for t, r in latest.items())),
                   tuple(sorted(profiles.items())),
                   tuple(sorted(weights.items())))
    return {'tasks': tasks, 'latest': latest, 'candidates': candidates,
            'profiles': profiles, 'weights': weights, 'fingerprint': fingerprint}


def _validate_match(plan, snapshot, user):
    if plan.state not in {'open', 'matched'} or not plan.rule_confirmed:
        raise HTTPException(409, '规则未确认或阶段不允许匹配')
    tasks = snapshot['tasks']
    if not tasks or not all(can(user, 'review', t) for t in tasks):
        raise HTTPException(403, '运行全计划匹配需要覆盖所有任务的审核授权')
    if not snapshot['latest']:
        raise HTTPException(409, '尚无教师提交意愿')


def _parse_ai_rankings(text):
    text = (text or '').strip()
    if text.startswith('```'):
        parts = text.split('\n', 1)
        text = parts[1] if len(parts) > 1 else ''
        if text.rstrip().endswith('```'):
            text = text.rstrip()[:-3]
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('AI 排序结果不是有效 JSON')
    try:
        data = json.loads(text[start:end + 1])
    except (TypeError, ValueError) as exc:
        raise ValueError('AI 排序结果不是有效 JSON') from exc
    if not isinstance(data, dict):
        raise ValueError('AI 排序结果不是有效 JSON')
    raw = data.get('rankings')
    if not isinstance(raw, list):
        raise ValueError('AI 排序结果格式不正确')
    rankings = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_ids = item.get('teacher_ids')
        if not isinstance(raw_ids, list):
            continue
        try:
            task_id = int(item.get('task_id'))
            ids = [int(x) for x in raw_ids]
        except (TypeError, ValueError):
            continue
        if ids:
            rankings[task_id] = list(dict.fromkeys(ids))
    if not rankings:
        raise ValueError('AI 排序结果为空')
    return rankings


def _ai_rank_candidates(db, snapshot):
    """让模型在规则评分基础上重排候选；失败时返回空排序并说明原因。"""
    config = resolve_config(db)
    if not config:
        return {}, {'used': False, 'reason': '未配置 AI 服务'}
    teacher_names = {t.id: t.name for t in db.query(Teacher)}
    tasks_payload = []
    for task in snapshot['tasks']:
        if task.get('locked'):
            continue
        pool = [c for c in snapshot['candidates'] if c['task_id'] == task['id'] and c.get('complete')]
        pool.sort(key=lambda c: (-(c.get('normalized_total') or 0), c['teacher_id']))
        top = pool[:10]
        if not top:
            continue
        tasks_payload.append({
            'task_id': task['id'], 'name': task['name'], 'code': task.get('code'),
            'group': task.get('group'), 'cohort': task.get('cohort'),
            'teacher_count': task.get('teacher_count', 1),
            'direction': task.get('direction'), 'tags': task.get('tags') or [],
            'candidates': [{
                'teacher_id': c['teacher_id'],
                'teacher_name': teacher_names.get(c['teacher_id'], ''),
                'rule_score': c.get('normalized_total'),
                'professional_fit': c.get('professional_fit'),
                'skilled_course_match': bool(c.get('skilled_course_match')),
                'eligible': bool(c.get('eligible')),
                'components': {comp.get('name'): comp.get('score') for comp in (c.get('components') or [])},
            } for c in top],
        })
    if not tasks_payload:
        return {}, {'used': False, 'reason': '没有可排序的候选任务'}
    system = ('你是学院排课系统的教师-课程匹配助手。根据任务、候选教师和系统规则权重，为每个任务排序候选教师。\n'
              '规则：\n'
              '- 只能使用每个任务 candidates 中出现过的 teacher_id。\n'
              '- 每个任务给出 teacher_count 个不同的 teacher_id，按推荐顺序排列。\n'
              '- 不要选择 eligible=false 的教师。\n'
              '- 优先综合得分高、专业方向匹配、余量充足的教师。\n'
              '- 只输出 JSON，不要输出解释性文字。\n'
              '格式：{"rankings":[{"task_id":1,"teacher_ids":[3],"reason":"..."}]}')
    user_text = '以下是任务、候选教师和系统规则权重：\n' + json.dumps(
        {'weights': snapshot['weights'], 'tasks': tasks_payload}, ensure_ascii=False)
    # 释放查询产生的读事务，避免模型调用期间占用 SQLite 读锁。
    db.rollback()
    try:
        result = call_llm(config, system, user_text, max_tokens=4000, json_mode=True)
        rankings = _parse_ai_rankings(result.get('text', ''))
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        return {}, {'used': False, 'reason': str(exc) or 'AI 排序失败',
                    'provider': config.get('provider'), 'model': config.get('model')}
    return rankings, {'used': True, 'reason': '', 'provider': config.get('provider'),
                      'model': result.get('model'), 'ranking_count': len(rankings)}


def _select_suggestions(db, plan, snapshot, ai_rankings=None):
    """AI 排序只改变候选顺序，每个选择仍重新执行意愿、回避与容量校验。"""
    ai_rankings = ai_rankings or {}
    candidates = snapshot['candidates']
    suggestions = []
    selected = {}
    ai_tasks = 0
    for task in sorted(snapshot['tasks'], key=lambda t: (sum(c['task_id'] == t['id'] for c in candidates), t['id'])):
        if task['locked']:
            suggestions.append({'task_id': task['id'], 'teacher_ids': task['teacher_ids'],
                                'locked': True, 'source': 'locked'})
            continue
        count = task['teacher_count']
        pool = sorted([c for c in candidates if c['task_id'] == task['id'] and c.get('complete')],
                      key=lambda c: (-(c.get('normalized_total') or 0), not c.get('skilled_course_match', False), c['teacher_id']))
        by_id = {c['teacher_id']: c for c in pool}
        choices = []
        ai_accepted = 0
        for tid in ai_rankings.get(task['id'], []):
            if tid in choices or tid not in by_id:
                continue
            reasons, _ = capacity(db, plan, task, tid, profile_for(db, tid),
                                  assigned_tasks(db, plan, tid, task['id']) + selected.get(tid, []))
            if not reasons:
                choices.append(tid)
                ai_accepted += 1
            if len(choices) == count:
                break
        if len(choices) < count:
            for candidate in pool:
                tid = candidate['teacher_id']
                if tid in choices:
                    continue
                reasons, _ = capacity(db, plan, task, tid, profile_for(db, tid),
                                      assigned_tasks(db, plan, tid, task['id']) + selected.get(tid, []))
                if not reasons:
                    choices.append(tid)
                if len(choices) == count:
                    break
        source = 'rule'
        if len(choices) != count:
            choices = []
        else:
            if ai_accepted:
                source = 'ai' if ai_accepted >= count else 'mixed'
                ai_tasks += 1
            for tid in choices:
                selected.setdefault(tid, []).append((task, plan))
        suggestions.append({'task_id': task['id'], 'teacher_ids': choices,
                            'locked': False, 'source': source})
    return suggestions, selected, ai_tasks


@router.post('/plans/{plan_id}/match')
def match(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db),use_ai:bool=Query(False)):
    if not can(user, 'admin') and any(g['capability']=='lead' for g in getattr(user,'grants',[])):
        raise HTTPException(403, '教研室主任不能运行全周期匹配，请由学院管理员统一运行')
    ai_rankings = {}
    ai_meta = None
    pre_fingerprint = None
    if use_ai:
        pre_plan = get_plan(db, plan_id)
        pre_snapshot = _match_snapshot(db, pre_plan)
        _validate_match(pre_plan, pre_snapshot, user)
        if not resolve_config(db):
            raise HTTPException(409, '请先在「AI 设置」中配置模型服务')
        pre_fingerprint = pre_snapshot['fingerprint']
        # 释放读取事务，避免模型调用期间占用数据库连接/锁。
        db.rollback()
        ai_rankings, ai_meta = _ai_rank_candidates(db, pre_snapshot)
    with write(db):
        plan = get_plan(db, plan_id)
        snapshot = _match_snapshot(db, plan)
        _validate_match(plan, snapshot, user)
        if use_ai and snapshot['fingerprint'] != pre_fingerprint:
            raise HTTPException(409, '匹配数据已变化，请重新运行 AI 排序')
        suggestions, _selected, ai_tasks = _select_suggestions(db, plan, snapshot, ai_rankings)
        ai_payload = {**(ai_meta or {'used': False, 'reason': '未启用 AI 排序'}), 'applied': ai_tasks}
        payload = {'plan_revision': plan.revision,
                   'submission_versions': {str(t): r.id for t, r in snapshot['latest'].items()},
                   'profile_versions': snapshot['profiles'], 'candidates': snapshot['candidates'],
                   'suggestions': suggestions, 'match_weights': snapshot['weights'],
                   'maximum': weights_total(snapshot['weights']), 'ai': ai_payload}
        row = MatchRun(plan_id=plan.id, payload=payload); db.add(row); db.flush()
        # AI/规则排序后自动落位；管理员在实时全学院课表中审核并人工调剂。
        task_by_id = {task['id']: task for task in snapshot['tasks']}
        auto_assigned = 0
        for suggestion in suggestions:
            task = task_by_id.get(suggestion['task_id'])
            if not task or suggestion.get('locked'):
                continue
            teacher_ids = suggestion.get('teacher_ids') or []
            if len(teacher_ids) == task['teacher_count']:
                db.add(TeachingAssignment(task_id=task['id'], teacher_ids=teacher_ids, match_id=row.id, locked=True))
                auto_assigned += 1
        plan.state = 'matched'
        event(db, user, 'match', {'match_id': row.id, 'auto_assigned': auto_assigned,
                                  'ai_used': bool(ai_payload.get('used')), 'ai_applied': ai_tasks}, plan.id)
        return {'id': row.id, 'auto_assigned': auto_assigned,
                'ai_used': bool(ai_payload.get('used')), 'ai_applied': ai_tasks,
                'ai_reason': ai_payload.get('reason', ''), **payload}


def _validate_assignment(db,plan,task,teacher_ids,run,user):
    """自动匹配审核与人工调剂共用同一套资格、回避和容量校验。"""
    if not task or task.plan_id!=plan.id:raise HTTPException(404,'任务不存在')
    details=task_dict(db,task);check(user,'review',details)
    if plan.state!='matched' or not run or run.plan_id!=plan.id or run.payload['plan_revision']!=plan.revision:raise HTTPException(409,'匹配批次过期')
    latest_run=db.query(MatchRun.id).filter_by(plan_id=plan.id).order_by(MatchRun.id.desc()).first()
    if latest_run[0]!=run.id:raise HTTPException(409,'请使用最新匹配批次')
    if len(teacher_ids)!=details['teacher_count'] or len(set(teacher_ids))!=len(teacher_ids):raise HTTPException(422,'教师人数与名额不符或重复')
    if getattr(user,'teacher_id',None) in teacher_ids:raise HTTPException(403,'本人申报必须回避，请交其他审核人')
    submissions=latest_submissions(db,plan.id)
    own_submission=submissions.get(getattr(user,'teacher_id',None))
    if own_submission and task.id in own_submission.task_ids:raise HTTPException(403,'本人申报的任务必须回避，请交其他审核人')
    for tid in teacher_ids:
        sub=submissions.get(tid);p=db.get(TeacherProfile,tid)
        if not sub or task.id not in sub.task_ids or run.payload['submission_versions'].get(str(tid))!=sub.id:raise HTTPException(409,'只能审核本批次已提交的意愿')
        if run.payload['profile_versions'].get(str(tid))!=(p.revision if p else 0):raise HTTPException(409,'教师画像已更新，请重新匹配')
        reasons,_=capacity(db,plan,details,tid,profile_for(db,tid),assigned_tasks(db,plan,tid,task.id))
        if reasons:raise HTTPException(409,'；'.join(reasons))
    return details


@router.post('/plans/{plan_id}/assign')
def assign(plan_id:int,data:AssignmentInput,user=Depends(require_user),db:Session=Depends(get_db)):
    with write(db):
        plan=get_plan(db,plan_id);task=db.get(TeachingTask,data.task_id);run=db.get(MatchRun,data.match_id)
        _validate_assignment(db,plan,task,data.teacher_ids,run,user)
        old=db.get(TeachingAssignment,task.id)
        if old:raise HTTPException(409,'此任务已审核锁定，不可覆盖；请使用人工调剂')
        db.add(TeachingAssignment(task_id=task.id,teacher_ids=data.teacher_ids,match_id=run.id,locked=True))
        event(db,user,'assign',data.model_dump(),plan.id)
        return {'success':True}


@router.put('/plans/{plan_id}/tasks/{task_id}/assignment')
def reassign(plan_id:int,task_id:int,data:ManualAssignmentInput,user=Depends(require_user),db:Session=Depends(get_db)):
    """管理员在实时全学院课表中人工调剂已审核任务的授课教师。"""
    with write(db):
        plan=get_plan(db,plan_id);task=db.get(TeachingTask,task_id);run=db.get(MatchRun,data.match_id)
        _validate_assignment(db,plan,task,data.teacher_ids,run,user)
        old=db.get(TeachingAssignment,task.id)
        if old:
            old.teacher_ids=data.teacher_ids;old.match_id=run.id;old.locked=True
        else:
            db.add(TeachingAssignment(task_id=task.id,teacher_ids=data.teacher_ids,match_id=run.id,locked=True))
        event(db,user,'reassign',{'task_id':task.id,**data.model_dump()},plan.id)
        return {'success':True,'task':task_dict(db,task)}


@router.post('/plans/{plan_id}/publish')
def publish(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'publish')
    with write(db):
        plan=get_plan(db,plan_id);tasks=[t for t in tasks_for(db,plan) if t.get('start_week')]
        if plan.state!='matched':raise HTTPException(409,'计划尚未完成匹配审核')
        # 发布只校验周段、地点、教师与教学组约束；周内节次为可选项，不要求也不校验。
        from app.api.stage_designer import validate_spans
        validate_tasks(db,plan,tasks,check_slots=False)
        validate_spans(plan,tasks,db)
        if not tasks or any(not t['locked'] or len(t['teacher_ids'])!=t['teacher_count'] or not t.get('room_id') for t in tasks):
            raise HTTPException(409,'尚有教师待审核或地点未落实')
        for task in tasks:
            for tid in task['teacher_ids']:
                reasons,_=capacity(db,plan,task,tid,profile_for(db,tid),assigned_tasks(db,plan,tid,task['id']))
                if reasons:raise HTTPException(409,'；'.join(reasons))
        names={t.id:t.name for t in db.query(Teacher)}
        for task in tasks:task['teacher_names']=[names.get(t,'') for t in task['teacher_ids']]
        plan.state='published';snapshot={'plan':plan_info(plan, db),'tasks':tasks}
        db.add(PublishedPlan(plan_id=plan.id,payload=snapshot));event(db,user,'publish',snapshot,plan.id)
        return {'success':True}


@router.get('/plans/{plan_id}/export')
def export_plan(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    return build_plan_excel(plan_id,user,db)


def build_plan_excel(plan_id,user,db,personal_teacher_id=None):
    from fastapi.responses import Response
    plan=get_plan(db,plan_id)
    snapshot=db.query(PublishedPlan).filter_by(plan_id=plan.id).order_by(PublishedPlan.id.desc()).first()
    if not snapshot:raise HTTPException(409,'只能导出已发布快照')
    tasks=snapshot.payload['tasks']
    if personal_teacher_id is not None:
        tasks=[t for t in tasks if personal_teacher_id in t['teacher_ids']]
        if not tasks:raise HTTPException(403,'该周期没有本人已发布课程')
    elif not (can(user,'admin') or can(user,'publish')):
        if can(user,'teaching',{'teacher_id':getattr(user,'teacher_id',None)}):
            tasks=[t for t in tasks if user.teacher_id in t['teacher_ids']]
        else:tasks=[t for t in tasks if can(user,'review',t)]
        if not tasks:raise HTTPException(403,'无可导出的本人或授权范围任务')
    from app.services.excel_timetable import build_visual_excel
    weeks=snapshot.payload['plan'].get('weeks',20)
    content=build_visual_excel([{'plan':snapshot.payload['plan'],'tasks':tasks,'snapshot_id':snapshot.id}],
        f'我的{weeks}周课表' if personal_teacher_id is not None else f'周期{weeks}周课表')
    return Response(content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition':f'attachment; filename="plan-{plan.id}-snapshot-{snapshot.id}.xlsx"','Cache-Control':'no-store'})


@router.get('/plans/{plan_id}/my-workload')
def my_workload(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    """管理员审核锁定授课安排后，按实际课时、人数基数和授课周数计算本人工作量。"""
    tid=teacher_access(user);plan=get_plan(db,plan_id)
    if plan.state=='draft':raise HTTPException(403,'计划尚未开放')
    return compute_teacher_workload(db,plan,tid,tasks_for(db,plan))


@router.get('/plans/{plan_id}/my-tasks')
def my_tasks(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    tid=teacher_access(user);plan=get_plan(db,plan_id)
    return [t for t in tasks_for(db,plan) if tid in t['teacher_ids']]


@router.get('/plans/{plan_id}/events')
def events(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    return [{'id':e.id,'actor':e.actor,'action':e.action,'payload':e.payload,'created_at':e.created_at}
            for e in db.query(PlanningEvent).filter_by(plan_id=plan_id).order_by(PlanningEvent.id)]


def _teacher_snapshot_task(db,plan_id,snapshot_id,task_id,teacher_id):
    plan=get_plan(db,plan_id)
    snapshot=db.get(PublishedPlan,snapshot_id)
    latest=db.query(PublishedPlan.id).filter_by(plan_id=plan_id).order_by(PublishedPlan.id.desc()).first()
    if plan.state!='published' or not snapshot or snapshot.plan_id!=plan_id or not latest or latest[0]!=snapshot_id:
        raise HTTPException(409,'课表快照已变化，请刷新后重试')
    task=next((row for row in snapshot.payload.get('tasks',[]) if row.get('id')==task_id),None)
    if not task or teacher_id not in task.get('teacher_ids',[]):raise HTTPException(403,'只能确认或申请调整本人已发布课程')
    return plan,snapshot,task


@router.post('/plans/{plan_id}/confirm-schedule')
def confirm_published_schedule(plan_id:int,data:ScheduleConfirmationInput,user=Depends(require_user),db:Session=Depends(get_db)):
    teacher_id=teacher_access(user);_plan,snapshot,task=_teacher_snapshot_task(db,plan_id,data.snapshot_id,data.task_id,teacher_id)
    existing=db.query(TeacherScheduleConfirmation).filter_by(snapshot_id=snapshot.id,task_id=data.task_id,teacher_id=teacher_id,status='confirmed').first()
    if existing:raise HTTPException(409,'此课程已确认')
    with write(db):
        row=TeacherScheduleConfirmation(snapshot_id=snapshot.id,plan_id=plan_id,task_id=data.task_id,
            teacher_id=teacher_id,status='confirmed',note=data.note.strip() or None)
        db.add(row);event(db,user,'teacher_confirm_schedule',{'snapshot_id':snapshot.id,'task_id':data.task_id},plan_id)
    return {'success':True,'confirmation_id':row.id}


@router.post('/plans/{plan_id}/change-requests')
def request_schedule_change(plan_id:int,data:ScheduleChangeRequestInput,user=Depends(require_user),db:Session=Depends(get_db)):
    teacher_id=teacher_access(user);_plan,snapshot,task=_teacher_snapshot_task(db,plan_id,data.snapshot_id,data.task_id,teacher_id)
    current=db.query(ScheduleChangeRequest).filter_by(snapshot_id=snapshot.id,task_id=data.task_id,teacher_id=teacher_id).all()
    if any(not db.query(ScheduleChangeDecision.id).filter_by(request_id=row.id).first() for row in current):
        raise HTTPException(409,'已有调课申请等待管理员处理')
    with write(db):
        row=ScheduleChangeRequest(snapshot_id=snapshot.id,plan_id=plan_id,task_id=data.task_id,teacher_id=teacher_id,
            reason=data.reason.strip(),desired_change=data.desired_change.strip() or None)
        db.add(row);db.flush();event(db,user,'schedule_change_requested',{'request_id':row.id,'task_id':data.task_id},plan_id)
    return {'success':True,'request_id':row.id,'task_name':task['name']}


@router.get('/plans/{plan_id}/change-requests')
def list_schedule_change_requests(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin');get_plan(db,plan_id);result=[]
    for row in db.query(ScheduleChangeRequest).filter_by(plan_id=plan_id).order_by(ScheduleChangeRequest.id.desc()):
        decision=db.query(ScheduleChangeDecision).filter_by(request_id=row.id).order_by(ScheduleChangeDecision.id.desc()).first()
        result.append({'id':row.id,'snapshot_id':row.snapshot_id,'task_id':row.task_id,'teacher_id':row.teacher_id,
            'reason':row.reason,'desired_change':row.desired_change,'status':decision.decision if decision else 'pending',
            'decision_reason':decision.reason if decision else None,'revision_plan_id':decision.revision_plan_id if decision else None})
    return result


@router.post('/plans/{plan_id}/change-requests/{request_id}/decision')
def decide_schedule_change(plan_id:int,request_id:int,data:ScheduleChangeDecisionInput,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        original=get_plan(db,plan_id);request=db.get(ScheduleChangeRequest,request_id)
        if not request or request.plan_id!=plan_id:raise HTTPException(404,'调课申请不存在')
        if db.query(ScheduleChangeDecision.id).filter_by(request_id=request.id).first():raise HTTPException(409,'该申请已处理')
        snapshot=db.get(PublishedPlan,request.snapshot_id)
        if not snapshot:raise HTTPException(409,'原课表快照不存在')
        revision_plan=None
        if data.approve:
            payload=snapshot.payload['plan'];settings={**(original.settings or {}),'supersedes_plan_id':original.id,'revision_of_snapshot_id':snapshot.id}
            revision_plan=AcademicPlan(name=f"{original.name} · 调整修订",start_date=original.start_date,weeks=original.weeks,
                deadline=datetime.utcnow()+timedelta(days=14),state='draft',rule_confirmed=True,settings=settings)
            db.add(revision_plan);db.flush()
            for source in snapshot.payload.get('tasks',[]):
                excluded={'id','plan_id','slots','teacher_ids','locked','room_name','teacher_names','applicants','applicant_count','actual_student_count'}
                task_payload={key:value for key,value in source.items() if key not in excluded}
                copied=TeachingTask(plan_id=revision_plan.id,payload=task_payload);db.add(copied);db.flush()
                for slot in source.get('slots',[]):
                    db.add(PeriodSlot(task_id=copied.id,day=slot['day'],start=slot['start'],count=slot['count'],phase=slot.get('phase','normal')))
            affected={teacher for task in snapshot.payload.get('tasks',[]) for teacher in task.get('teacher_ids',[])}
            for teacher_id in affected:
                db.add(TeacherNotification(teacher_id=teacher_id,plan_id=revision_plan.id,kind='schedule_revision',
                    payload={'request_id':request.id,'supersedes_plan_id':original.id,'message':'调课申请已批准，请在修订周期重新确认授课安排。'}))
        else:
            db.add(TeacherNotification(teacher_id=request.teacher_id,plan_id=plan_id,kind='change_request_rejected',
                payload={'request_id':request.id,'message':data.reason.strip() or '调课申请未获批准'}))
        decision=ScheduleChangeDecision(request_id=request.id,admin_actor=f"{'demo' if getattr(user, 'is_demo', False) else 'user'}:{user.id}",
            decision='approved' if data.approve else 'rejected',reason=data.reason.strip() or None,
            revision_plan_id=revision_plan.id if revision_plan else None)
        db.add(decision);event(db,user,'schedule_change_decided',{'request_id':request.id,'decision':decision.decision,
            'revision_plan_id':decision.revision_plan_id},plan_id)
    return {'success':True,'decision':decision.decision,'revision_plan_id':decision.revision_plan_id}


@router.get('/my-notifications')
def my_planning_notifications(user=Depends(require_user),db:Session=Depends(get_db)):
    teacher_id=teacher_access(user)
    return [{'id':row.id,'plan_id':row.plan_id,'kind':row.kind,'payload':row.payload,'created_at':row.created_at}
        for row in db.query(TeacherNotification).filter_by(teacher_id=teacher_id).order_by(TeacherNotification.id.desc())]


@router.get('/history/published')
def published_history(user=Depends(require_user), db: Session=Depends(get_db)):
    if not can(user, 'admin'):
        raise HTTPException(403, '仅管理员可查看全部历史课表')
    latest = {}
    for snapshot in db.query(PublishedPlan).order_by(PublishedPlan.id.desc()):
        if snapshot.plan_id not in latest:
            latest[snapshot.plan_id] = {'snapshot_id': snapshot.id, **snapshot.payload}
    return list(latest.values())
