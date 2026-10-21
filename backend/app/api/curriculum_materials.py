import hashlib
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.planning import CurriculumDocument, ActiveCurriculum, TeachingTask
from app.services.auth import require_user
from app.services.authorization import check
from app.services.curriculum_materials import extract_rows
from app.services.course_library import sync_courses
from app.services.academic_scope import is_global, plan_term, program_semester, groups_for_curriculum
from app.api.planning import write, get_plan, event, tasks_for

router=APIRouter(prefix='/api/planning',tags=['培养方案原件与版本'])


def serialize(db,doc):
    active=db.query(ActiveCurriculum).filter_by(document_id=doc.id).first()
    return {'id':doc.id,'name':doc.name,'major':doc.major,'cohort':doc.cohort,'revision':doc.revision,
            'sha256':doc.sha256,'rows':doc.rows,'active':bool(active)}


@router.get('/curricula')
def curricula(user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    return [serialize(db,doc) for doc in db.query(CurriculumDocument).order_by(CurriculumDocument.id.desc())]


@router.post('/curricula/import')
async def import_curriculum(major:str=Form(...),cohort:str=Form(...),revision:int=Form(...),
        file:UploadFile=File(...),user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    major=major.strip();cohort=cohort.strip()
    if not major or not cohort or revision<1:raise HTTPException(422,'专业、届次和修订号必填')
    content=await file.read(10*1024*1024+1)
    # scope 参与系统内部课程编码生成，确保不同专业/届次/修订号的同名课程不会碰撞
    rows,errors=extract_rows(file.filename or '',content,f'{major}|{cohort}|{revision}')
    if errors:raise HTTPException(422,'；'.join(errors[:20]))
    with write(db):
        if db.query(CurriculumDocument).filter_by(major=major,cohort=cohort,revision=revision).first():raise HTTPException(409,'该专业届次修订号已存在，原件不会覆盖')
        doc=CurriculumDocument(name=(file.filename or 'source')[:200],major=major.strip(),cohort=cohort.strip(),revision=revision,
            original=content,sha256=hashlib.sha256(content).hexdigest(),rows=rows)
        db.add(doc);db.flush();event(db,user,'import_curriculum',{'document_id':doc.id,'sha256':doc.sha256})
        return serialize(db,doc)


@router.post('/curricula/{document_id}/activate')
def activate(document_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        doc=db.get(CurriculumDocument,document_id)
        if not doc:raise HTTPException(404,'方案不存在')
        report=sync_courses(db,doc)
        current=db.query(ActiveCurriculum).filter_by(major=doc.major,cohort=doc.cohort).first()
        if current:current.document_id=doc.id
        else:db.add(ActiveCurriculum(major=doc.major,cohort=doc.cohort,document_id=doc.id))
        event(db,user,'activate_curriculum',{'document_id':doc.id})
        return {'success':True,'course_library':report}


@router.post('/curricula/{document_id}/sync-courses')
def sync_existing(document_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        doc=db.get(CurriculumDocument,document_id)
        if not doc:raise HTTPException(404,'方案不存在')
        if not db.query(ActiveCurriculum).filter_by(document_id=doc.id).first():raise HTTPException(409,'请核对并启用方案后同步课程库')
        report=sync_courses(db,doc);event(db,user,'sync_course_library',{'document_id':doc.id,**report})
        return report


@router.get('/curricula/{document_id}/source')
def source(document_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin');doc=db.get(CurriculumDocument,document_id)
    if not doc:raise HTTPException(404,'原件不存在')
    return Response(doc.original,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="curriculum-{doc.id}.{doc.name.rsplit(".",1)[-1]}"'})


def _curriculum_scope(db,plan):
    """返回要生成任务的培养方案、培养学期与教学组；全学院周期覆盖全部已启用方案。"""
    config=plan.settings or {}
    if not is_global(plan):
        if not config.get('major') or not config.get('cohort') or not config.get('groups'):
            raise HTTPException(422,'周期须设置专业、入学届次、班级和培养学期')
        active=db.query(ActiveCurriculum).filter_by(major=config['major'],cohort=config['cohort']).first()
        if not active:raise HTTPException(409,'该专业届次没有已启用培养方案')
        doc=db.get(CurriculumDocument,active.document_id)
        return [(doc,config.get('semester'),list(config.get('groups') or []))]
    term=plan_term(plan);allowed=list(config.get('groups') or []);result=[]
    for active in db.query(ActiveCurriculum).order_by(ActiveCurriculum.id):
        doc=db.get(CurriculumDocument,active.document_id)
        semester=program_semester(plan.start_date,term,active.cohort)
        if doc and semester:
            result.append((doc,semester,groups_for_curriculum(db,doc.major,doc.cohort,allowed or None)))
    return result


@router.post('/plans/{plan_id}/generate')
def generate(plan_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        plan=get_plan(db,plan_id)
        if plan.state!='draft':raise HTTPException(409,'非草稿计划不能重新生成')
        scope=_curriculum_scope(db,plan)
        if not scope:raise HTTPException(409,'没有可用的已启用培养方案或届次无法匹配当前学期')
        existing=tasks_for(db,plan);keys={(t['code'],t['group']) for t in existing};added=0;skipped=[]
        for doc,semester,groups in scope:
            if not doc:continue
            sync_courses(db,doc)
            rows=[r for r in doc.rows if r['semester']==semester and r.get('schedulable',True)
                  and (not r.get('category') or r['category'].startswith('专业'))]
            if not groups:
                skipped.append(f'{doc.major} {doc.cohort}：未在班级数据中找到对应教学组')
                continue
            if not rows:
                skipped.append(f'{doc.major} {doc.cohort}：第{semester}学期没有可生成的专业课程')
                continue
            for group in dict.fromkeys(groups):
                for row in rows:
                    if (row['code'],group) in keys:continue
                    payload={k:row[k] for k in ['name','code','credits','required_hours','direction','tags']}
                    metadata={k:v for k,v in row.items() if k not in payload}
                    payload.update(group=group,department=doc.major,class_name=group,student_ids=[],
                        major=doc.major,cohort=doc.cohort,program_semester=semester,
                        start_week=None,end_week=None,tail_weeks=0,teacher_count=1,mode='single',student_count=0,
                        room_id=None,room_type='',profile_verified=False,
                        source={'document_id':doc.id,'revision':doc.revision,'sha256':doc.sha256,'major':doc.major,'cohort':doc.cohort,'course_metadata':metadata})
                    db.add(TeachingTask(plan_id=plan.id,payload=payload));added+=1
        if added:plan.revision+=1
        db.flush();event(db,user,'generate_tasks',{'documents':len(scope),'added':added,'skipped':skipped},plan.id)
        return {'task_count':len(existing)+added,'added':added,'needs_schedule':True,'documents':len(scope),'skipped':skipped}
