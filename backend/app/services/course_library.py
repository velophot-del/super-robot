from app.models.course import Course
from app.models.planning import CurriculumCourse,CurriculumDocument,OfferingUnit

COURSE_TYPES = {'专业课','学科通识课','德育通识课','综合实践课','跨专业交叉课','国际课程'}
COURSE_NATURES = {'必修课','限选课','任选课'}
# 学科通识课/德育通识课属于公共课，默认不进入课程库列表与排课课程池。
PUBLIC_COURSE_TYPES = ('学科通识课', '德育通识课')
PUBLIC_COURSE_KEYWORDS = ('公共', '通识', '德育', '思政')


def is_public_course(course_type=None):
    """判断课程类型是否属于公共课；兼容历史未归一的“公共课/思政课”等写法。"""
    text = (course_type or '').strip()
    return text in PUBLIC_COURSE_TYPES or any(word in text for word in PUBLIC_COURSE_KEYWORDS)


def public_course_clause():
    """SQLAlchemy 条件：命中公共课；空类型按非公共课处理。"""
    from sqlalchemy import func, or_
    course_type = func.coalesce(Course.course_type, '')
    return or_(course_type.in_(PUBLIC_COURSE_TYPES),
               *[course_type.like(f'%{word}%') for word in PUBLIC_COURSE_KEYWORDS])


def normalize_course_classification(raw_type='', raw_nature=''):
    raw_type=(raw_type or '').strip()
    raw_nature=(raw_nature or '').strip()
    course_type=raw_type if raw_type in COURSE_TYPES else (
        '国际课程' if '国际' in raw_type else
        '跨专业交叉课' if '交叉' in raw_type or '跨专业' in raw_type else
        '德育通识课' if '德育' in raw_type or '思政' in raw_type else
        '综合实践课' if '实践' in raw_type else
        '学科通识课' if '公共' in raw_type or '通识' in raw_type else '专业课')
    nature_text=raw_nature or raw_type
    course_nature=(raw_nature if raw_nature in COURSE_NATURES else
        '任选课' if '任选' in nature_text else
        '限选课' if any(value in nature_text for value in ('限选','选修')) else '必修课')
    return course_type,course_nature


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
        unit=db.get(OfferingUnit,c.offering_unit_id) if c.offering_unit_id else None
        c.offering_unit_name=unit.name if unit else None
    return courses


def professional_courses(db):
    return [c for c in db.query(Course).order_by(Course.name,Course.course_code)
            if c.course_type in {'专业课','专业','专业必修','专业选修','必修','选修'}]
