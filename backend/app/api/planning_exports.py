"""Authorized major-level Word exports, always from immutable published snapshots."""
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
        if not tasks or not plan.get('major'):continue
        result.append({'plan':plan,'tasks':tasks,'snapshot_id':row.id})
    return result


@router.get('/options')
def export_options(user=Depends(require_user),db:Session=Depends(get_db)):
    return [{'major':b['plan']['major'],'start_date':b['plan']['start_date'],'weeks':b['plan']['weeks'],
             'cohort':b['plan'].get('cohort',''),'term':academic_title(b['plan']),
             'plan_id':b['plan']['id'],'snapshot_id':b['snapshot_id']} for b in published_batches(db,user)]


@router.get('/word')
def export_word(major:str=Query(min_length=1,max_length=200),start_date:date=Query(),
                weeks:int=Query(ge=18,le=20),cohort:str|None=None,
                user=Depends(require_user),db:Session=Depends(get_db)):
    batches=[b for b in published_batches(db,user) if b['plan']['major']==major
        and b['plan']['start_date']==start_date.isoformat() and b['plan']['weeks']==weeks
        and (cohort is None or b['plan'].get('cohort','')==cohort)]
    if not batches:raise HTTPException(404,'所选专业、周期和年级没有可导出的已发布课表')
    if len({academic_title(b['plan']) for b in batches})!=1:raise HTTPException(409,'所选快照学年学期不一致，请先核对排课周期设置')
    content=build_word_timetable(batches,major)
    filename=quote(f'{major}_{start_date}_专业课总表.docx',safe='')
    return Response(content,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition':f"attachment; filename=professional-timetable.docx; filename*=UTF-8''{filename}",
                 'Cache-Control':'no-store'})
