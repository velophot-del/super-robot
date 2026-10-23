"""Authorized major-level Word exports, always from immutable published snapshots."""
from collections import defaultdict
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.planning import PublishedPlan
from app.services.auth import require_user
from app.services.authorization import can
from app.services.word_timetable import build_word_timetable,academic_title

router=APIRouter(prefix='/api/planning/exports',tags=['专业课表模板导出'])


def visible_tasks(user,tasks):
    if can(user,'admin') or can(user,'publish'):return tasks
    teacher_id=getattr(user,'teacher_id',None)
    return [t for t in tasks if (can(user,'teaching',{'teacher_id':teacher_id}) and teacher_id in t.get('teacher_ids',[])) or can(user,'review',t)]


def published_batches(db,user):
    latest={}
    for row in db.query(PublishedPlan).order_by(PublishedPlan.id):latest[row.plan_id]=row
    result=[]
    for row in latest.values():
        payload=row.payload;plan=payload['plan'];tasks=visible_tasks(user,payload['tasks'])
        if not tasks:continue
        result.append({'plan':plan,'tasks':tasks,'snapshot_id':row.id})
    return result


@router.get('/options')
def export_options(user=Depends(require_user),db:Session=Depends(get_db)):
    result=[]
    for batch in published_batches(db,user):
        plan=batch['plan']
        pairs=sorted({(task.get('major') or plan.get('major') or '',
                       str(task.get('cohort') or plan.get('cohort') or '')) for task in batch['tasks']})
        for major,cohort in pairs:
            if not major:continue
            result.append({'major':major,'start_date':plan['start_date'],'weeks':plan['weeks'],
                'cohort':cohort,'term':academic_title(plan),
                'plan_id':plan['id'],'snapshot_id':batch['snapshot_id']})
    return result


@router.get('/word')
def export_word(major:str=Query(min_length=1,max_length=200),start_date:date=Query(),
                weeks:int=Query(ge=18,le=20),cohort:str|None=None,
                user=Depends(require_user),db:Session=Depends(get_db)):
    batches=[];synth=[]
    for batch in published_batches(db,user):
        plan=batch['plan']
        if plan['start_date']!=start_date.isoformat() or plan['weeks']!=weeks:continue
        tasks=[task for task in batch['tasks']
               if (task.get('major') or plan.get('major') or '')==major
               and (cohort is None or str(task.get('cohort') or plan.get('cohort') or '')==cohort)]
        if tasks:batches.append({**batch,'tasks':tasks})
    if not batches:raise HTTPException(404,'所选专业、周期和年级没有可导出的已发布课表')
    if len({academic_title(b['plan']) for b in batches})!=1:raise HTTPException(409,'所选快照学年学期不一致，请先核对排课周期设置')
    # 全学院周期一个快照包含多个届次，按届次拆分分页。
    for batch in batches:
        by_cohort=defaultdict(list)
        for task in batch['tasks']:
            by_cohort[str(task.get('cohort') or batch['plan'].get('cohort') or '未设置年级')].append(task)
        for name,tasks in by_cohort.items():
            synth.append({**batch,'plan':{**batch['plan'],'cohort':name},'tasks':tasks})
    content=build_word_timetable(synth,major)
    filename=quote(f'{major}_{start_date}_专业课总表.docx',safe='')
    return Response(content,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition':f"attachment; filename=professional-timetable.docx; filename*=UTF-8''{filename}",
                 'Cache-Control':'no-store'})


@router.get('/college/{plan_id}')
def export_college(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    if not can(user,'admin'):raise HTTPException(403,'仅管理员可导出全学院课表')
    latest={}
    for snapshot in db.query(PublishedPlan).order_by(PublishedPlan.id):latest[snapshot.plan_id]=snapshot
    selected=latest.get(plan_id)
    if not selected:raise HTTPException(409,'所选周期尚无已发布课表')
    plan=selected.payload['plan']
    batches=[{**s.payload,'snapshot_id':s.id} for s in latest.values()
        if s.payload['plan']['start_date']==plan['start_date'] and s.payload['plan']['weeks']==plan['weeks']]
    from app.services.excel_timetable import build_visual_excel
    content=build_visual_excel(batches,f"全学院{plan.get('weeks',20)}周课表")
    return Response(content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':f'attachment; filename="college-plan-{plan_id}.xlsx"','Cache-Control':'no-store'})
