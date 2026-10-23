from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.planning import AcademicPlan,TeachingTask,PeriodSlot,AutoSchedulePreview
from app.models.course import Course
from app.models.class_info import ClassInfo
from app.services.auth import require_user
from app.services.authorization import check
from app.services.stage_planning import task_dict,validate_tasks,validate_student_limit
from app.services.academic_scope import is_global, plan_term, groups_for_cycle
from app.services.course_catalog import course_catalog_scope, course_pool_rows
from app.services.exam_weeks import exam_weeks_for
from app.api.planning import write,get_plan,tasks_for,event

router=APIRouter(prefix='/api/planning/plans',tags=['管理员阶段课表设计'])


class PlacementInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    course_id:int|None=None
    task_id:int|None=None
    document_id:int|None=None
    group:str=Field(min_length=1,max_length=100)
    start_week:int=Field(ge=1,le=20)
    duration:int|None=Field(None,ge=1,le=20)


class GroupsInput(BaseModel):
    revision:int=Field(ge=1)
    groups:list[str]=Field(min_length=1,max_length=100)


class AutoSchedulePreviewInput(BaseModel):
    algorithm:str=Field('genetic',pattern='^(genetic|backtracking)$')


class AutoScheduleApplyInput(BaseModel):
    preview_id:int=Field(ge=1)


def pool_rows(db,plan):
    settings=plan.settings or {}
    if is_global(plan):
        scope=course_catalog_scope(db,plan.start_date,plan_term(plan),settings.get('groups') or None)
    else:
        scope=course_catalog_scope(db,plan.start_date,plan_term(plan),settings.get('groups') or None,
            settings.get('major'),settings.get('cohort'),settings.get('semester'))
    return [],course_pool_rows(scope)


def validate_spans(plan,tasks):
    weekly=defaultdict(list)
    for task in tasks:
        if not task.get('start_week'):continue
        if task['start_week']>task['end_week'] or task['end_week']>plan.weeks:raise HTTPException(409,'课程周段越界')
        exam=exam_weeks_for(plan,task.get('cohort'),task.get('group'),plan.weeks)
        blocked=sorted(exam & set(range(task['start_week'],task['end_week']+1)))
        if blocked:raise HTTPException(409,f"课程不能进入该年级考试周（第{'、'.join(map(str,blocked))}周）")
        keys=['student:'+s for s in task.get('student_ids',[])] or ['group:'+(task.get('class_name') or task['group'])]
        for week in range(task['start_week'],task['end_week']+1):
            for key in keys:
                entries=weekly[(key,week)]
                if task['code'] in entries:raise HTTPException(409,'该班级同一课程周段重复，请编辑已有课程')
                entries.append(task['code'])
                if len(entries)>2:raise HTTPException(409,'同一班级每周最多2门课程')


@router.get('/{plan_id}/course-pool')
def course_pool(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin');plan=get_plan(db,plan_id);documents,rows=pool_rows(db,plan)
    return {'document_id':None,'document_ids':[],'revision':None,
            'global_cycle':is_global(plan),'courses':rows}


@router.post('/{plan_id}/auto-schedule')
def auto_schedule(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin');plan=get_plan(db,plan_id)
    from app.services.auto_placement import generate_auto_placement
    return generate_auto_placement(db,plan,user)


@router.post('/{plan_id}/auto-schedule/preview')
def preview_auto_schedule(plan_id:int,data:AutoSchedulePreviewInput,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin');plan=get_plan(db,plan_id)
    from app.services.auto_placement import build_auto_schedule_candidate
    candidate=build_auto_schedule_candidate(db,plan,data.algorithm)
    with write(db):
        row=AutoSchedulePreview(plan_id=plan.id,plan_revision=plan.revision,algorithm=data.algorithm,
            payload=candidate,expires_at=datetime.utcnow()+timedelta(minutes=30))
        db.add(row);db.flush()
        return {**candidate,'preview_id':row.id,'expires_at':row.expires_at.isoformat()+'Z',
            'plan_revision':row.plan_revision}


@router.post('/{plan_id}/auto-schedule/apply')
def apply_auto_schedule(plan_id:int,data:AutoScheduleApplyInput,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin');plan=get_plan(db,plan_id);preview=db.get(AutoSchedulePreview,data.preview_id)
    if not preview or preview.plan_id!=plan.id:raise HTTPException(404,'排课候选不存在')
    from app.services.auto_placement import apply_auto_schedule_candidate
    return apply_auto_schedule_candidate(db,plan,user,preview.payload,preview)


@router.put('/{plan_id}/groups')
def update_groups(plan_id:int,data:GroupsInput,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state=='published':raise HTTPException(409,'已发布周期的班级已冻结')
        if plan.revision!=data.revision:raise HTTPException(409,'版本已变化，请刷新')
        groups=list(dict.fromkeys(g.strip() for g in data.groups if g.strip()))
        if not groups or any(len(g)>100 for g in groups):raise HTTPException(422,'请填写有效班级名称')
        eligible=None
        if is_global(plan):
            eligible=set(groups_for_cycle(db,plan.start_date,plan_term(plan)))
            known={row.name for row in db.query(ClassInfo).filter(ClassInfo.is_active.is_(True))}
            if any(group in known and group not in eligible for group in groups):
                raise HTTPException(422,'当前周期不能加入已毕业或未纳入培养方案的班级')
        if any(t.payload['group'] not in groups and t.payload.get('start_week')
               and (eligible is None or t.payload['group'] in eligible)
               for t in db.query(TeachingTask).filter_by(plan_id=plan.id)):
            raise HTTPException(409,'已有排课的班级不能移除')
        plan.settings={**(plan.settings or {}),'groups':groups}
        # 开放/匹配阶段增加班级不影响既有任务和志愿，不递增版本，避免已提交意愿失效。
        if plan.state=='draft':plan.revision+=1
        event(db,user,'set_groups',{'groups':groups},plan.id);return {'revision':plan.revision}


@router.put('/{plan_id}/placement')
def place_course(plan_id:int,data:PlacementInput,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state!='draft' or plan.revision!=data.revision:raise HTTPException(409,'周期已锁定或版本变化，请刷新')
        groups=(plan.settings or {}).get('groups',[])
        if data.group not in groups:raise HTTPException(422,'请先在本周期设置开课班级')
        if bool(data.course_id)==bool(data.task_id):raise HTTPException(422,'请选择一门课程或已有课程块')
        tasks=tasks_for(db,plan);task=None
        if data.task_id:
            task=db.get(TeachingTask,data.task_id)
            if not task or task.plan_id!=plan.id:raise HTTPException(404,'课程任务不存在')
            payload=dict(task.payload);meta=payload.get('source',{}).get('course_metadata',{})
            duration=data.duration or ((payload['end_week']-payload['start_week']+1) if payload.get('start_week') else meta.get('teaching_weeks'))
        else:
            _,rows=pool_rows(db,plan)
            candidates=[row for row in rows if row['id']==data.course_id and data.group in row.get('groups',[])]
            if not candidates:raise HTTPException(409,'该课程不适用于本周期班级，请检查课程库中的专业、年级和上课学期')
            row=candidates[0]
            course=db.get(Course,data.course_id)
            if not course or not course.is_active:raise HTTPException(409,'课程已停用或不存在，请刷新课程库')
            task=next((db.get(TeachingTask,t['id']) for t in tasks
                       if t['code']==row['code'] and t['group']==data.group and not t.get('start_week')
                       and t.get('source',{}).get('course_id')==course.id),None)
            payload=dict(task.payload) if task else {k:row[k] for k in ['name','code','credits','required_hours','direction','tags']}
            meta={k:v for k,v in row.items() if k not in {'id','document_id','major','cohort','groups'}}
            duration=data.duration or row.get('teaching_weeks')
            payload.update(source={'course_id':course.id,'major':row['major'],'cohort':row['cohort'],'course_metadata':meta})
        if not duration:raise HTTPException(422,'方案未注明上课周数，请先明确课程占用周数')
        old_group=payload.get('group')
        department=payload.get('department') or (row.get('major') if not data.task_id else '') or (plan.settings or {}).get('major','')
        payload.update(group=data.group,class_name=data.group,department=department,
            start_week=data.start_week,end_week=data.start_week+duration-1,tail_weeks=payload.get('tail_weeks',0) if data.task_id else (1 if meta.get('tail_hours') and duration>1 else 0),
            teacher_count=payload.get('teacher_count',1),mode=payload.get('mode','single'),profile_verified=payload.get('profile_verified',False),
            # 实际选课人数不在排课阶段预设；移动到新班级时清空旧人数。
            student_count=payload.get('student_count',0) if old_group==data.group else 0,
            student_ids=payload.get('student_ids',[]) if old_group==data.group else [],
            room_id=payload.get('room_id'),room_type=payload.get('room_type',''))
        if not data.task_id:
            payload.update(major=row['major'],cohort=row['cohort'],program_semester=row['semester'])
        slots=[{'day':s.day,'start':s.start,'count':s.count,'phase':s.phase} for s in db.query(PeriodSlot).filter_by(task_id=task.id)] if task else []
        candidate={**payload,'slots':slots}
        others=[t for t in tasks if not task or t['id']!=task.id]
        validate_spans(plan,[*others,candidate])
        validate_student_limit(db,candidate)
        complete=[t for t in [*others,candidate] if t.get('start_week') and t.get('slots')]
        if complete:validate_tasks(db,plan,complete)
        if task:task.payload=payload
        else:task=TeachingTask(plan_id=plan.id,payload=payload);db.add(task)
        db.flush();plan.revision+=1;event(db,user,'place_course',{'task_id':task.id,'group':data.group,'start_week':data.start_week,'duration':duration},plan.id)
        return {'revision':plan.revision,'task':task_dict(db,task)}


@router.delete('/{plan_id}/placement/{task_id}')
def unplace_course(plan_id:int,task_id:int,revision:int=Query(ge=1),user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id);task=db.get(TeachingTask,task_id)
        if plan.state!='draft' or plan.revision!=revision:raise HTTPException(409,'周期已锁定或版本变化')
        if not task or task.plan_id!=plan.id:raise HTTPException(404,'任务不存在')
        task.payload={**task.payload,'start_week':None,'end_week':None};db.query(PeriodSlot).filter_by(task_id=task.id).delete()
        plan.revision+=1;event(db,user,'unplace_course',{'task_id':task.id},plan.id)
        return {'revision':plan.revision}
