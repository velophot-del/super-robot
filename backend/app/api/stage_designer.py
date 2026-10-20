from collections import defaultdict
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.planning import AcademicPlan,TeachingTask,PeriodSlot,CurriculumDocument,ActiveCurriculum,CurriculumCourse
from app.models.course import Course
from app.models.class_info import ClassInfo
from app.services.auth import require_user
from app.services.authorization import check
from app.services.stage_planning import task_dict,validate_tasks
from app.services.course_library import sync_courses
from app.api.planning import write,get_plan,tasks_for,event

router=APIRouter(prefix='/api/planning/plans',tags=['管理员阶段课表设计'])


class PlacementInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    course_id:int|None=None
    task_id:int|None=None
    group:str=Field(min_length=1,max_length=100)
    start_week:int=Field(ge=1,le=20)
    duration:int|None=Field(None,ge=1,le=20)


class GroupsInput(BaseModel):
    revision:int=Field(ge=1)
    groups:list[str]=Field(min_length=1,max_length=100)


def active_document(db,plan):
    config=plan.settings or {}
    active=db.query(ActiveCurriculum).filter_by(major=config.get('major',''),cohort=config.get('cohort','')).first()
    return db.get(CurriculumDocument,active.document_id) if active else None


def pool_rows(db,plan):
    doc=active_document(db,plan)
    if not doc:return None,[]
    links={l.row_code:l for l in db.query(CurriculumCourse).filter_by(document_id=doc.id)}
    result=[]
    for row in doc.rows:
        if row.get('semester')!=(plan.settings or {}).get('semester') or not row.get('schedulable',True) or (row.get('category') and not row['category'].startswith('专业')):continue
        link=links.get(row['code'])
        if not link:continue
        course=db.get(Course,link.course_id)
        if not course:continue
        result.append({'id':course.id,**row})
    return doc,result


def validate_spans(plan,tasks):
    weekly=defaultdict(list)
    for task in tasks:
        if not task.get('start_week'):continue
        if task['start_week']>task['end_week'] or task['end_week']>plan.weeks-1:raise HTTPException(409,'课程周段越界或进入最后一周考试周')
        keys=['student:'+s for s in task.get('student_ids',[])] or ['group:'+(task.get('class_name') or task['group'])]
        for week in range(task['start_week'],task['end_week']+1):
            for key in keys:
                entries=weekly[(key,week)]
                if task['code'] in entries:raise HTTPException(409,'该班级同一课程周段重复，请编辑已有课程')
                entries.append(task['code'])
                if len(entries)>2:raise HTTPException(409,'同一班级每周最多2门课程')


@router.get('/{plan_id}/course-pool')
def course_pool(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin');plan=get_plan(db,plan_id);doc,rows=pool_rows(db,plan)
    return {'document_id':doc.id if doc else None,'revision':doc.revision if doc else None,'courses':rows}


@router.post('/{plan_id}/sync-course-pool')
def sync_pool(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id);doc=active_document(db,plan)
        if not doc:raise HTTPException(409,'该专业届次还没有已启用培养方案')
        report=sync_courses(db,doc);event(db,user,'sync_course_library',{'document_id':doc.id,**report},plan.id)
        return report


@router.put('/{plan_id}/groups')
def update_groups(plan_id:int,data:GroupsInput,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state!='draft' or plan.revision!=data.revision:raise HTTPException(409,'周期已锁定或版本变化，请刷新')
        groups=list(dict.fromkeys(g.strip() for g in data.groups if g.strip()))
        if not groups or any(len(g)>100 for g in groups):raise HTTPException(422,'请填写有效班级名称')
        if any(t.payload['group'] not in groups and t.payload.get('start_week') for t in db.query(TeachingTask).filter_by(plan_id=plan.id)):raise HTTPException(409,'已有排课的班级不能移除')
        plan.settings={**(plan.settings or {}),'groups':groups};plan.revision+=1
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
            doc,rows=pool_rows(db,plan);row=next((r for r in rows if r['id']==data.course_id),None)
            if not row:raise HTTPException(409,'该课程不属于本周期生效培养方案的可排课程，请先同步课程库')
            course=db.get(Course,data.course_id)
            if course.name!=row['name'] or course.total_hours!=row['required_hours'] or float(course.credits or 0)!=float(row['credits']):raise HTTPException(409,'课程库与培养方案属性不一致，请先核对')
            task=next((db.get(TeachingTask,t['id']) for t in tasks if t['code']==row['code'] and t['group']==data.group and not t.get('start_week')),None)
            payload=dict(task.payload) if task else {k:row[k] for k in ['name','code','credits','required_hours','direction','tags']}
            meta={k:v for k,v in row.items() if k!='id'};duration=data.duration or row.get('teaching_weeks')
            payload.update(source={'document_id':doc.id,'revision':doc.revision,'sha256':doc.sha256,'major':doc.major,'cohort':doc.cohort,'course_id':course.id,'course_metadata':meta})
        if not duration:raise HTTPException(422,'方案未注明上课周数，请先明确课程占用周数')
        old_group=payload.get('group')
        roster=db.query(ClassInfo).filter_by(name=data.group).first()
        payload.update(group=data.group,class_name=data.group,department=payload.get('department') or (plan.settings or {}).get('major',''),
            start_week=data.start_week,end_week=data.start_week+duration-1,tail_weeks=payload.get('tail_weeks',0) if data.task_id else (1 if meta.get('tail_hours') and duration>1 else 0),
            teacher_count=payload.get('teacher_count',1),mode=payload.get('mode','single'),profile_verified=payload.get('profile_verified',False),
            student_count=roster.student_count if roster else payload.get('student_count',30),student_ids=payload.get('student_ids',[]) if old_group==data.group else [],
            room_id=payload.get('room_id'),room_type=payload.get('room_type',''))
        slots=[{'day':s.day,'start':s.start,'count':s.count,'phase':s.phase} for s in db.query(PeriodSlot).filter_by(task_id=task.id)] if task else []
        candidate={**payload,'slots':slots}
        others=[t for t in tasks if not task or t['id']!=task.id]
        validate_spans(plan,[*others,candidate])
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
