"""课程管理API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.course import Course
from app.models.planning import OfferingUnit, AcademicDirection, AcademicProgram
from app.services.course_library import attach_sources, public_course_clause
from app.schemas.course import CourseCreate, CourseUpdate, CourseResponse
from app.services.auth import require_user
from app.services.authorization import check

router = APIRouter(prefix="/api/courses", tags=["课程管理"])


class CourseBulkUpdateInput(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    updates: CourseUpdate


class CourseBulkRemoveInput(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class OfferingUnitInput(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)


@router.get("/", response_model=List[CourseResponse], summary="获取课程列表")
def list_courses(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    course_type: str = Query(None),
    department: str = Query(None),
    search: str = Query(None),
    cohort: str = Query(None),
    course_nature: str = Query(None),
    include_inactive: bool = Query(False),
    include_public: bool = Query(False),
    db: Session = Depends(get_db),
):
    query = db.query(Course)
    if not include_inactive:
        query = query.filter(Course.is_active.is_(True))
    # 公共课默认从课程库列表隐藏；需要查看或恢复时显式传入 include_public=true。
    if not include_public:
        query = query.filter(~public_course_clause())
    if course_type:
        query = query.filter(Course.course_type == course_type)
    if department:
        query = query.filter(Course.department == department)
    if search:
        query = query.filter(Course.name.contains(search))
    if cohort:
        query = query.filter(Course.cohort == cohort)
    if course_nature:
        query = query.filter(Course.course_nature == course_nature)
    return attach_sources(db,query.offset(skip).limit(limit).all())


@router.patch('/bulk', summary='批量修改课程')
def bulk_update_courses(data: CourseBulkUpdateInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    ids = list(dict.fromkeys(data.ids))
    updates = data.updates.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(422, '请至少选择一个要批量修改的字段')
    if 'course_code' in updates or 'name' in updates:
        raise HTTPException(422, '课程名称和编码不能对多门课程设置相同值，请逐门编辑')
    courses = db.query(Course).filter(Course.id.in_(ids)).all()
    if len(courses) != len(ids):
        raise HTTPException(404, '部分课程不存在，请刷新列表后重试')
    if 'leader_teacher_id' in updates:
        validate_leader(db, updates['leader_teacher_id'])
    if 'offering_unit_id' in updates:
        validate_offering_unit(db, updates['offering_unit_id'])
    validate_course_scope(db, updates, partial=True)
    try:
        for course in courses:
            normalized = normalize_course_scope(db, course, updates)
            for key, value in normalized.items():
                setattr(course, key, value)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'updated': len(courses), 'ids': ids}


@router.delete('/bulk', summary='批量移出课程库')
def bulk_remove_courses(data: CourseBulkRemoveInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    ids = list(dict.fromkeys(data.ids))
    courses = db.query(Course).filter(Course.id.in_(ids)).all()
    if len(courses) != len(ids):
        raise HTTPException(404, '部分课程不存在，请刷新列表后重试')
    for course in courses:
        course.is_active = False
    db.commit()
    return {'removed': len(courses), 'ids': ids, 'mode': 'soft'}


@router.get('/offering-units', summary='获取开课单位')
def list_offering_units(db: Session = Depends(get_db)):
    return [{'id': unit.id, 'code': unit.code, 'name': unit.name, 'is_active': unit.is_active}
            for unit in db.query(OfferingUnit).order_by(OfferingUnit.name)]


@router.post('/offering-units', summary='新增开课单位')
def create_offering_unit(data: OfferingUnitInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    code, name = data.code.strip(), data.name.strip()
    if db.query(OfferingUnit).filter((OfferingUnit.code == code) | (OfferingUnit.name == name)).first():
        raise HTTPException(409, '开课单位编码或名称已存在')
    unit = OfferingUnit(code=code, name=name)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return {'id': unit.id, 'code': unit.code, 'name': unit.name, 'is_active': unit.is_active}


@router.get("/{course_id}", response_model=CourseResponse, summary="获取课程详情")
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return attach_sources(db,[course])[0]


@router.post("/", response_model=CourseResponse, status_code=201, summary="创建课程")
def create_course(data: CourseCreate, db: Session = Depends(get_db)):
    existing = db.query(Course).filter(Course.course_code == data.course_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"课程编码'{data.course_code}'已存在")
    validate_leader(db,data.leader_teacher_id)
    validate_offering_unit(db,data.offering_unit_id)
    values=normalize_course_scope(db, None, data.model_dump())
    course = Course(**values)
    db.add(course)
    db.commit()
    db.refresh(course)
    return attach_sources(db,[course])[0]


@router.put("/{course_id}", response_model=CourseResponse, summary="更新课程")
def update_course(course_id: int, data: CourseUpdate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    update_data = data.model_dump(exclude_unset=True)
    if 'leader_teacher_id' in update_data:validate_leader(db,data.leader_teacher_id)
    if 'offering_unit_id' in update_data:validate_offering_unit(db,data.offering_unit_id)
    update_data=normalize_course_scope(db, course, update_data)
    for key, value in update_data.items():
        setattr(course, key, value)
    db.commit()
    db.refresh(course)
    return attach_sources(db,[course])[0]


@router.delete("/{course_id}", summary="删除课程")
def delete_course(course_id: int, db: Session = Depends(get_db)):
    """从活动课程库移出；历史课程来源及已生成课表仍保留。"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    course.is_active = False
    db.commit()
    return {"ok": True, "message": f"课程「{course.name}」已移出活动课程库"}


def validate_leader(db, teacher_id):
    from app.models.teacher import Teacher
    if teacher_id is not None and not db.get(Teacher, teacher_id):
        raise HTTPException(422,'课程负责人不存在，请重新选择教师')


def validate_offering_unit(db,unit_id):
    if unit_id is not None and not db.get(OfferingUnit,unit_id):
        raise HTTPException(422,'开课单位不存在')


def validate_course_scope(db, values, partial=False):
    program_id=values.get('program_id')
    direction_id=values.get('direction_id')
    if program_id is not None and not db.get(AcademicProgram,program_id):
        raise HTTPException(422,'所选专业不存在，请从管理员专业目录选择')
    if direction_id is not None:
        direction=db.get(AcademicDirection,direction_id)
        if not direction:raise HTTPException(422,'所选专业方向不存在，请从管理员专业目录选择')
        if program_id is not None and direction.program_id!=program_id:
            raise HTTPException(422,'专业方向不属于所选专业')


def normalize_course_scope(db, course, values):
    result=dict(values)
    current_program=getattr(course,'program_id',None) if course else None
    current_direction=getattr(course,'direction_id',None) if course else None
    program_id=result.get('program_id',current_program)
    direction_id=result.get('direction_id',current_direction)
    if 'department' in result and result.get('department') and 'program_id' not in result:
        legacy=db.query(AcademicProgram).filter_by(name=str(result['department']).strip()).first()
        if legacy:
            program_id=legacy.id;result['program_id']=legacy.id
        elif db.query(AcademicProgram.id).first():
            raise HTTPException(422,'适用专业不在管理员专业目录中，请从目录选择')
    if 'program_id' in result and program_id is None:
        direction_id=None
        result['direction_id']=None
    elif 'program_id' in result and program_id!=current_program and 'direction_id' not in result:
        direction_id=None
        result['direction_id']=None
    validate_course_scope(db,{**result,'program_id':program_id,'direction_id':direction_id})
    if direction_id is not None:
        direction=db.get(AcademicDirection,direction_id)
        result['program_id']=direction.program_id
        if direction.offering_unit_id:
            result['offering_unit_id']=direction.offering_unit_id
    elif program_id is not None:
        result['program_id']=program_id
    final_program=result.get('program_id',current_program)
    if final_program is not None:
        program=db.get(AcademicProgram,final_program)
        result['department']=program.name
        if 'direction_id' not in result and 'program_id' in result and final_program!=current_program:
            result['direction_id']=None
    elif 'program_id' in result and result['program_id'] is None:
        result['department']=None
        result['direction_id']=None
    return result
