"""教师先申报的阶段式计划工作流。所有决定来自事务内最新版本。"""
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.teacher import Teacher
from app.models.classroom import Classroom
from app.models.class_info import ClassInfo
from app.models.planning import (AcademicPlan, TeachingTask, PeriodSlot, TeacherProfile,
    PreferenceDraft, PreferenceSubmission, MatchRun, TeachingAssignment, PlanningEvent, PublishedPlan, TeacherWorkloadEstimate)
from app.schemas.planning import PlanInput, TaskInput, TaskLimitsInput, RoomInput, ActualStudentsInput, ExamWeeksInput, MatchWeightsInput, ProfileInput, DraftInput, SubmitInput, AssignmentInput, ManualAssignmentInput, SelfProfileInput, WorkloadEstimateInput
from app.services.auth import require_user
from app.services.authorization import can, check
from app.services.stage_planning import task_dict, validate_tasks, validate_student_limit, capacity
from app.services.academic_scope import is_global, plan_term, program_semester
from app.services.exam_weeks import normalize_exam_weeks, exam_weeks_from_config
from app.services.matching_weights import get_match_weights, weight_items, weights_total
from app.services.workload import compute_teacher_workload
from app.services.teacher_course_matching import score_candidate
from app.services.personal_profile import require_personal_profile,missing_profile_fields,effective_profile

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
    return [task_dict(db, task) for task in rows]


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
    return any(g['capability'] in {'admin', 'review', 'publish', 'teaching'} for g in getattr(user,'grants',[]))


def plan_info(plan):
    return {'id':plan.id, 'name':plan.name, 'start_date':plan.start_date.isoformat(),
            'weeks':plan.weeks, 'deadline':plan.deadline.isoformat()+'Z', 'state':plan.state,
            'revision':plan.revision, 'rule_confirmed':plan.rule_confirmed, **(plan.settings or {}),
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
        from datetime import timedelta
        if other.id == plan.id or (other.state == 'published' and other.start_date < plan.start_date+timedelta(weeks=plan.weeks)
                and other.start_date+timedelta(weeks=other.weeks) > plan.start_date): chosen.append((task_dict(db,task),other))
    return chosen


@router.get('/plans')
def list_plans(user=Depends(require_user), db: Session=Depends(get_db)):
    if not can_read(user): raise HTTPException(403, '账号尚未授予工作职能')
    return [plan_info(p) for p in db.query(AcademicPlan).order_by(AcademicPlan.id.desc())
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
            # 全学院周期默认纳入所有班级；管理员仍可在课表编排页增删教学组。
            settings.update({'global': True, 'term': data.term})
            if not settings['groups']:
                settings['groups']=[row.name for row in db.query(ClassInfo).order_by(ClassInfo.id)]
        else:
            settings.update(major=data.major,cohort=data.cohort,semester=data.semester)
        plan=AcademicPlan(name=data.name,start_date=data.start_date,weeks=data.weeks,
                          deadline=deadline.astimezone(timezone.utc).replace(tzinfo=None),rule_confirmed=data.rule_confirmed,
                          settings=settings)
        db.add(plan); db.flush(); event(db,user,'create_plan',data.model_dump(mode='json'),plan.id)
        return plan_info(plan)


@router.get('/plans/{plan_id}')
def get_state(plan_id: int, user=Depends(require_user), db: Session=Depends(get_db)):
    plan=get_plan(db,plan_id)
    if not can_read(user) or (plan.state=='draft' and not can(user,'admin')): raise HTTPException(403,'计划尚未开放')
    all_tasks=tasks_for(db,plan)
    if not can(user,'admin'):all_tasks=[t for t in all_tasks if t.get('start_week') and t.get('end_week')]
    tasks=[t for t in all_tasks if can(user,'admin') or can(user,'publish') or
           can(user,'teaching',{'teacher_id':getattr(user,'teacher_id',None)}) or can(user,'review',t)]
    names={t.id:t.name for t in db.query(Teacher)}
    for task in tasks: task['teacher_names']=[names.get(t,'') for t in task['teacher_ids']]
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
            if c['teacher_id']==teacher_id or can(user,'review',task): candidates.append({**c,'teacher_name':names.get(c['teacher_id'],'')})
    estimates={r.task_id:{**r.payload,'revision':r.revision} for r in db.query(TeacherWorkloadEstimate).filter_by(plan_id=plan.id,teacher_id=teacher_id)} if teacher_id else {}
    weights=get_match_weights(plan)
    return {**plan_info(plan),'tasks':tasks,'workload_estimates':estimates,
        'match_weights':weights,'match_weight_items':weight_items(weights),'match_weight_total':weights_total(weights),
        'draft':{'revision':draft.revision,'task_ids':draft.task_ids,'plan_revision':draft.plan_revision} if draft else {'revision':0,'task_ids':[],'plan_revision':plan.revision},
        'submission':{'id':submitted.id,'task_ids':submitted.task_ids} if submitted else None,
        'submission_count':len(latest) if can(user,'admin') or any(can(user,'review',t) for t in tasks) else None,
        'match':{'id':run.id,'maximum':run.payload.get('maximum',weights_total(weights)),'weights':run.payload.get('match_weights',weights),
            'candidates':candidates,'suggestions':[
            s for s in run.payload['suggestions'] if any(t['id']==s['task_id'] and can(user,'review',t) for t in tasks)]} if run else None}


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


@router.get('/self-profile/courses')
def own_course_catalog(user=Depends(require_user),db:Session=Depends(get_db)):
    teacher_access(user)
    from app.models.planning import CurriculumDocument,ActiveCurriculum
    names={task.payload['name'] for task in db.query(TeachingTask).join(AcademicPlan).filter(AcademicPlan.state!='draft')}
    for doc in db.query(CurriculumDocument).join(ActiveCurriculum,ActiveCurriculum.document_id==CurriculumDocument.id):
        names.update(r['name'] for r in doc.rows if not r.get('category') or r['category'].startswith('专业'))
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
        validate_spans(plan,[*tasks,payload])
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
                if payload[key]!=task.payload[key]:raise HTTPException(409,'来源课程属性不可覆盖，请派生培养方案修订')
            payload['source']=task.payload['source']
        from app.api.stage_designer import validate_spans
        all_others=[t for t in tasks_for(db,plan) if t['id']!=task_id]
        validate_spans(plan,[*all_others,payload])
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
        validate_spans(plan,tasks)
        for task in tasks:validate_student_limit(db,task)
        if any(not isinstance(t.get('required_hours'),int) or t['required_hours']<=0 for t in tasks):
            raise HTTPException(409,'请先核对课程计划学时')
        plan.state='open';event(db,user,'open',{},plan.id)
        return plan_info(plan)


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


@router.put('/plans/{plan_id}/exam-weeks')
def set_exam_weeks(plan_id:int,data:ExamWeeksInput,user=Depends(require_user),db:Session=Depends(get_db)):
    """按年级/教学组设置考试周；未配置的年级沿用最后一周考试。"""
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state=='published':raise HTTPException(409,'已发布周期的考试周已冻结')
        try:normalized=normalize_exam_weeks(data.exam_weeks,plan.weeks)
        except ValueError as e:raise HTTPException(422,str(e))
        conflicts=[]
        for task in tasks_for(db,plan):
            if not task.get('start_week') or not task.get('end_week'):continue
            exam=exam_weeks_from_config(normalized,plan.settings,task.get('cohort'),task.get('group'),plan.weeks)
            blocked=sorted(exam & set(range(task['start_week'],task['end_week']+1)))
            if blocked:conflicts.append(f"{task['name']}（{task['group']}）第{'、'.join(map(str,blocked))}周")
        if conflicts:raise HTTPException(409,'以下课程已排入考试周，请先调整周段：'+'；'.join(conflicts))
        plan.settings={**(plan.settings or {}),'exam_weeks':normalized}
        db.flush();event(db,user,'set_exam_weeks',normalized,plan.id)
        return {'exam_weeks':normalized}


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


@router.post('/plans/{plan_id}/match')
def match(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    with write(db):
        plan=get_plan(db,plan_id);tasks=[t for t in tasks_for(db,plan) if t.get('start_week')]
        if not tasks or not all(can(user,'review',t) for t in tasks):raise HTTPException(403,'运行全计划匹配需要覆盖所有任务的审核授权')
        if plan.state not in {'open','matched'} or not plan.rule_confirmed:raise HTTPException(409,'规则未确认或阶段不允许匹配')
        latest=latest_submissions(db,plan.id)
        if not latest:raise HTTPException(409,'尚无教师提交意愿')
        candidates=[];profiles={};suggestions=[];selected={}
        for tid,submission in latest.items():
            if submission.plan_revision!=plan.revision:raise HTTPException(409,'存在过时申报，请先处理')
            profile=profile_for(db,tid);p=db.get(TeacherProfile,tid);profiles[str(tid)]=p.revision if p else 0
            for task_id in submission.task_ids:
                task=next(t for t in tasks if t['id']==task_id)
                candidates.append(score_candidate(db,plan,task,tid,profile,assigned_tasks(db,plan,tid,task_id)))
        for task in sorted(tasks,key=lambda t:(sum(c['task_id']==t['id'] for c in candidates),t['id'])):
            if task['locked']:
                suggestions.append({'task_id':task['id'],'teacher_ids':task['teacher_ids'],'locked':True});continue
            choices=[]
            pool=sorted([c for c in candidates if c['task_id']==task['id'] and c['complete']],
                        key=lambda c:(-(c['normalized_total'] or 0),not c.get('skilled_course_match',False),c['teacher_id']))
            for candidate in pool:
                tid=candidate['teacher_id'];chosen=assigned_tasks(db,plan,tid,task['id'])+selected.get(tid,[])
                reasons,_=capacity(db,plan,task,tid,profile_for(db,tid),chosen)
                if not reasons: choices.append(tid)
                if len(choices)==task['teacher_count']:break
            if len(choices)==task['teacher_count']:
                for tid in choices:selected.setdefault(tid,[]).append((task,plan))
            else:choices=[]
            suggestions.append({'task_id':task['id'],'teacher_ids':choices,'locked':False})
        weights=get_match_weights(plan)
        payload={'plan_revision':plan.revision,'submission_versions':{str(t):r.id for t,r in latest.items()},
                 'profile_versions':profiles,'candidates':candidates,'suggestions':suggestions,
                 'match_weights':weights,'maximum':weights_total(weights)}
        row=MatchRun(plan_id=plan.id,payload=payload);db.add(row);db.flush()
        # 系统按规则自动落位匹配结果；管理员在实时全学院课表中审核并人工调剂。
        task_by_id={task['id']:task for task in tasks}
        auto_assigned=0
        for suggestion in suggestions:
            task=task_by_id.get(suggestion['task_id'])
            if not task or suggestion.get('locked'):continue
            teacher_ids=suggestion.get('teacher_ids') or []
            if len(teacher_ids)==task['teacher_count']:
                db.add(TeachingAssignment(task_id=task['id'],teacher_ids=teacher_ids,match_id=row.id,locked=True))
                auto_assigned+=1
        plan.state='matched'
        event(db,user,'match',{'match_id':row.id,'auto_assigned':auto_assigned},plan.id)
        return {'id':row.id,'auto_assigned':auto_assigned,**payload}


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
        validate_spans(plan,tasks)
        if not tasks or any(not t['locked'] or len(t['teacher_ids'])!=t['teacher_count'] or not t.get('room_id') for t in tasks):
            raise HTTPException(409,'尚有教师待审核或地点未落实')
        for task in tasks:
            for tid in task['teacher_ids']:
                reasons,_=capacity(db,plan,task,tid,profile_for(db,tid),assigned_tasks(db,plan,tid,task['id']))
                if reasons:raise HTTPException(409,'；'.join(reasons))
        names={t.id:t.name for t in db.query(Teacher)}
        for task in tasks:task['teacher_names']=[names.get(t,'') for t in task['teacher_ids']]
        plan.state='published';snapshot={'plan':plan_info(plan),'tasks':tasks}
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


@router.get('/history/published')
def published_history(user=Depends(require_user), db: Session=Depends(get_db)):
    if not can(user, 'admin'):
        raise HTTPException(403, '仅管理员可查看全部历史课表')
    latest = {}
    for snapshot in db.query(PublishedPlan).order_by(PublishedPlan.id.desc()):
        if snapshot.plan_id not in latest:
            latest[snapshot.plan_id] = {'snapshot_id': snapshot.id, **snapshot.payload}
    return list(latest.values())
