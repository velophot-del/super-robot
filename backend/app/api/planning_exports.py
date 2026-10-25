"""Major-level Word exports for published snapshots and process/blank drafts."""
from collections import defaultdict
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.planning import AcademicPlan, PublishedPlan
from app.models.teacher import Teacher
from app.services.auth import require_user
from app.services.authorization import can
from app.services.word_timetable import build_word_timetable,academic_title

router=APIRouter(prefix='/api/planning/exports',tags=['专业课表模板导出'])


def export_batches(db):
    """Export every cycle: immutable snapshot when published, current tasks otherwise."""
    latest={}
    for row in db.query(PublishedPlan).order_by(PublishedPlan.id):
        latest[row.plan_id]=row
    names={teacher.id:teacher.name for teacher in db.query(Teacher)}
    result=[]
    for plan in db.query(AcademicPlan).order_by(AcademicPlan.id):
        snapshot=latest.get(plan.id) if plan.state=='published' else None
        if snapshot:
            payload=snapshot.payload or {}
            plan_payload=payload.get('plan') or {}
            tasks=list(payload.get('tasks') or [])
            source='published';snapshot_id=snapshot.id
        else:
            from app.api.planning import plan_info,tasks_for
            plan_payload=plan_info(plan,db)
            tasks=tasks_for(db,plan)
            source='current';snapshot_id=None
        for task in tasks:
            if not task.get('teacher_names'):
                task['teacher_names']=[names.get(tid,f'教师{tid}')
                                       for tid in (task.get('teacher_ids') or [])]
            if not task.get('major'):
                task['major']=plan_payload.get('major') or task.get('department') or ''
            if not task.get('cohort'):
                task['cohort']=plan_payload.get('cohort') or ''
        result.append({'plan':plan_payload,'tasks':tasks,'snapshot_id':snapshot_id,
                       'source':source,'state':plan.state})
    return result


@router.get('/options')
def export_options(user=Depends(require_user),db:Session=Depends(get_db)):
    """List every cycle, including draft/open/matched process drafts and blank drafts."""
    result=[]
    for batch in export_batches(db):
        plan=batch['plan']
        pairs={(task.get('major') or plan.get('major') or '',
                str(task.get('cohort') or plan.get('cohort') or '')) for task in batch['tasks']}
        if not pairs:pairs.add((plan.get('major') or '',str(plan.get('cohort') or '')))
        for major,cohort in sorted(pairs):
            result.append({'major':major,'start_date':plan['start_date'],'weeks':plan['weeks'],
                'cohort':cohort,'term':academic_title(plan),'plan_id':plan['id'],
                'plan_name':plan.get('name') or '', 'state':batch['state'],
                'source':batch['source'],'snapshot_id':batch['snapshot_id']})
    return result


@router.get('/word')
def export_word(major:str=Query(default='',max_length=200),start_date:date=Query(),
                weeks:int=Query(ge=18,le=20),cohort:str|None=None,plan_id:int|None=None,blank:bool=False,
                user=Depends(require_user),db:Session=Depends(get_db)):
    batches=[];synth=[]
    if blank:
        from app.services.academic_scope import current_academic_term
        candidates=[{'plan':{'id':0,'name':'空白模板','start_date':start_date.isoformat(),
            'weeks':weeks,'major':major,'cohort':cohort or '',
            'term':current_academic_term(start_date)},'tasks':[],'source':'blank','state':'draft'}]
    else:
        candidates=export_batches(db)
    if plan_id is not None and not blank:
        candidates=[batch for batch in candidates if batch['plan'].get('id')==plan_id]
        if not candidates:raise HTTPException(404,'所选周期不存在')
    elif not blank:
        from app.services.plan_versions import superseded_plan_ids
        superseded = superseded_plan_ids(db)
        candidates = [batch for batch in candidates if batch['plan']['id'] not in superseded]
    for batch in candidates:
        plan=batch['plan']
        if plan['start_date']!=start_date.isoformat() or plan['weeks']!=weeks:continue
        if major and batch['tasks']:
            available={(task.get('major') or plan.get('major') or '') for task in batch['tasks']}
            if major not in available:continue
        tasks=[task for task in batch['tasks']
               if (not major or (task.get('major') or plan.get('major') or '')==major)
               and (cohort is None or str(task.get('cohort') or plan.get('cohort') or '')==cohort)]
        # Keep empty batches so process drafts and blank drafts still produce a template.
        batches.append({**batch,'tasks':tasks})
    if not batches:raise HTTPException(404,'所选专业、周期和年级没有可导出的课表')
    if len({academic_title(b['plan']) for b in batches})!=1:raise HTTPException(409,'所选周期学年学期不一致，请先核对排课周期设置')
    # 全学院周期一个周期包含多个届次，按届次拆分分页。
    for batch in batches:
        by_cohort=defaultdict(list)
        for task in batch['tasks']:
            by_cohort[str(task.get('cohort') or batch['plan'].get('cohort') or '未设置年级')].append(task)
        if not by_cohort:
            by_cohort[str(batch['plan'].get('cohort') or '未设置年级')]=[]
        for name,tasks in by_cohort.items():
            synth.append({**batch,'plan':{**batch['plan'],'cohort':name},'tasks':tasks})
    title_major=major or next((b['plan'].get('major') for b in batches if b['plan'].get('major')),'未设置专业')
    content=build_word_timetable(synth,title_major)
    filename=quote(f'{title_major}_{start_date}_专业课总表.docx',safe='')
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
