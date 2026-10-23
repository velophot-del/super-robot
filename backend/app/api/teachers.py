"""教师管理API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.teacher import Teacher
from app.models.schedule import ScheduleEntry
from app.models.course import Course
from app.models.class_info import ClassInfo
from app.models.planning import TeacherProfile
from app.services.course_library import professional_courses
from app.services.course_catalog import course_schedule_info
from app.services.schedule_versions import resolve_schedule_version
from app.schemas.teacher import TeacherCreate, TeacherUpdate, TeacherResponse

router = APIRouter(prefix="/api/teachers", tags=["教师管理"])


@router.get("/", response_model=List[TeacherResponse], summary="获取教师列表")
def list_teachers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    department: str = Query(None),
    search: str = Query(None),
    db: Session = Depends(get_db),
):
    """获取所有教师"""
    query = db.query(Teacher)
    if department:
        query = query.filter(Teacher.department == department)
    if search:
        query = query.filter(Teacher.name.contains(search))
    return query.offset(skip).limit(limit).all()


# ⚠️ 重要：/{teacher_id}/courses 必须放在 /{teacher_id} 前面，否则会被后者拦截
@router.get("/{teacher_id}/courses", summary="查看教师课程分配")
def get_teacher_courses(teacher_id: int, version: str = Query(None), db: Session = Depends(get_db)):
    """查看某教师分配的所有课程及各课程学时（需先执行排课）"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    # 未指定版本时固定到最新版本，避免多个版本的排课条目相互叠加。
    version = resolve_schedule_version(db, version)
    entries = [] if not version else db.query(ScheduleEntry).filter(
        ScheduleEntry.teacher_id == teacher_id,
        ScheduleEntry.schedule_version == version,
    ).all()

    if not entries:
        return {
            "teacher_id": teacher_id, "teacher_name": teacher.name,
            "department": teacher.department, "title": teacher.title,
            "courses": [], "total_weekly_hours": 0,
        }

    # 按课程+班级聚合
    course_map = {}
    for entry in entries:
        key = (entry.course_id, entry.class_id)
        if key not in course_map:
            course = db.query(Course).filter(Course.id == entry.course_id).first()
            cls = db.query(ClassInfo).filter(ClassInfo.id == entry.class_id).first()
            info = course_schedule_info(course) if course else {
                'teaching_weeks': 0, 'weekdays': [], 'total_hours': 0, 'weekly_hours': 0}
            course_map[key] = {
                "course_id": entry.course_id,
                "course_name": course.name if course else "",
                "course_code": course.course_code if course else "",
                "teaching_weeks": info['teaching_weeks'],
                "weekdays": info['weekdays'],
                "total_hours": info['total_hours'],
                "weekly_hours": info['weekly_hours'],
                "class_name": cls.name if cls else "",
                "time_slots": 0,
            }
        course_map[key]["time_slots"] += 1

    courses = []
    total = 0
    for key, info in course_map.items():
        courses.append({
            "course_id": info["course_id"],
            "course_name": info["course_name"],
            "course_code": info["course_code"],
            "teaching_weeks": info["teaching_weeks"],
            "weekdays": info["weekdays"],
            "total_hours": info["total_hours"],
            "weekly_hours": info["weekly_hours"],
            "class_name": info["class_name"],
            "time_slots": info["time_slots"],
        })
        total += info["weekly_hours"]

    return {
        "teacher_id": teacher_id, "teacher_name": teacher.name,
        "department": teacher.department, "title": teacher.title,
        "courses": courses, "total_weekly_hours": total,
    }


def _course_summary(course):
    return {'id': course.id, 'name': course.name, 'course_code': course.course_code,
            'department': course.department, 'course_type': course.course_type}


@router.get("/{teacher_id}/course-affiliations", summary="查看教师课程组与课程负责人")
def get_teacher_course_affiliations(teacher_id: int, db: Session = Depends(get_db)):
    """打通教师个人资料与课程管理：只读展示参与课程组及本人负责的专业课程。"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    professional = {course.id: course for course in professional_courses(db)}
    profile = db.get(TeacherProfile, teacher_id)
    own = (profile.payload.get('self_profile') or {}) if profile else {}
    group_ids = [int(cid) for cid in (own.get('participating_course_ids') or []) if str(cid).isdigit()]
    course_groups = [_course_summary(professional[cid]) for cid in dict.fromkeys(group_ids) if cid in professional]
    leader_courses = [_course_summary(course) for course in professional.values()
                      if course.leader_teacher_id == teacher_id]
    leader_courses.sort(key=lambda course: (course['name'], course['course_code']))
    return {'teacher_id': teacher.id, 'teacher_name': teacher.name,
            'profile_updated': bool(own), 'course_groups': course_groups,
            'leader_courses': leader_courses}


@router.get("/{teacher_id}", response_model=TeacherResponse, summary="获取教师详情")
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    return teacher


@router.post("/", response_model=TeacherResponse, status_code=201, summary="创建教师")
def create_teacher(data: TeacherCreate, db: Session = Depends(get_db)):
    existing = db.query(Teacher).filter(
        (Teacher.teacher_code == data.teacher_code) | (Teacher.email == data.email)
    ).first() if data.email else db.query(Teacher).filter(
        Teacher.teacher_code == data.teacher_code
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="教师工号或邮箱已存在")
    from app.services.teacher_positions import validate_position
    validate_position(data.position, data.review_major)
    teacher = Teacher(**data.model_dump())
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.put("/{teacher_id}", response_model=TeacherResponse, summary="更新教师")
def update_teacher(teacher_id: int, data: TeacherUpdate, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    update_data = data.model_dump(exclude_unset=True)
    from app.services.teacher_positions import validate_position
    validate_position(update_data.get('position', teacher.position),
                      update_data.get('review_major', teacher.review_major))
    for key, value in update_data.items():
        setattr(teacher, key, value)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}", summary="删除教师")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """删除教师（如有排课引用则阻止删除并提示）"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    ref_count = db.query(ScheduleEntry).filter(ScheduleEntry.teacher_id == teacher_id).count()
    if ref_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"无法删除教师「{teacher.name}」：该教师有 {ref_count} 条排课记录引用，请先删除相关排课方案后再操作"
        )

    db.delete(teacher)
    db.commit()
    return {"ok": True, "message": f"教师「{teacher.name}」已删除"}
