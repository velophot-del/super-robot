from fastapi import HTTPException
from app.models.course import Course
from app.models.planning import CurriculumCourse,CurriculumDocument,ActiveCurriculum
from app.utils.departments import merge_department


def sync_courses(db,doc):
    added=reused=skipped=0
    for row in doc.rows:
        if row.get('record_type')=='review' or row['name'] in {'课程单独列出','合计','小计','总计'}:skipped+=1;continue
        existing=db.query(Course).filter_by(course_code=row['code']).first()
        if existing and (existing.name!=row['name'] or float(existing.credits or 0)!=float(row['credits']) or existing.total_hours!=row['required_hours']):
            raise HTTPException(409,f"课程编码{row['code']}与课程库内容冲突，未覆盖，请先核对原件和课程库")
        if not existing:
            category=row.get('category','')
            existing=Course(name=row['name'],course_code=row['code'],credits=row['credits'],total_hours=row['required_hours'],
                department=doc.major,course_type=category or '必修',semester_sessions=1,weekly_sessions=1,hours_per_session=1,
                remarks=row.get('notes',''))
            db.add(existing);db.flush();added+=1
        else:
            # 同一课程编码可能被多个专业共享；合并专业归属，避免后启用的专业覆盖先前的专业
            merged=merge_department(existing.department,doc.major)
            if merged!=existing.department:existing.department=merged
            reused+=1
        link=db.query(CurriculumCourse).filter_by(document_id=doc.id,row_code=row['code']).first()
        if not link:db.add(CurriculumCourse(document_id=doc.id,row_code=row['code'],course_id=existing.id,metadata_json=row))
    db.flush()
    return {'added':added,'reused':reused,'skipped_placeholders':skipped}


def attach_sources(db,courses):
    ids=[c.id for c in courses];sources={cid:[] for cid in ids}
    if ids:
        for link,doc in db.query(CurriculumCourse,CurriculumDocument).join(CurriculumDocument,CurriculumCourse.document_id==CurriculumDocument.id).filter(CurriculumCourse.course_id.in_(ids)).order_by(CurriculumDocument.id.desc()):
            sources[link.course_id].append({'document_id':doc.id,'major':doc.major,'cohort':doc.cohort,'revision':doc.revision,'metadata':link.metadata_json})
    from app.models.teacher import Teacher
    leader_ids={c.leader_teacher_id for c in courses if c.leader_teacher_id is not None}
    leaders={t.id:t for t in db.query(Teacher).filter(Teacher.id.in_(leader_ids))} if leader_ids else {}
    for c in courses:
        c.curriculum_sources=sources[c.id]
        leader=leaders.get(c.leader_teacher_id)
        c.leader_teacher_name=leader.name if leader else None
        c.leader_teacher_code=leader.teacher_code if leader else None
    return courses


def professional_courses(db):
    return [c for c in db.query(Course).order_by(Course.name,Course.course_code)
            if (c.course_type or '').startswith('专业') or c.course_type in {'必修','选修','实践课'}]
