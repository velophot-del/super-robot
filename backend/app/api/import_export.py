"""数据导入导出API"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
import io
from urllib.parse import quote

from app.database import get_db
from app.models.class_info import ClassInfo
from app.models.teacher import Teacher
from app.models.course import Course
from app.models.classroom import Classroom
from app.models.schedule import ScheduleEntry
from app.utils.csv_parser import parse_csv_content, generate_csv_template, parse_syllabus_csv
from app.services.validation import ValidationService
from app.services.export_service import ExportService
from app.services.conflict import ConflictDetector
from app.services.explanation import ExplanationGenerator
from app.services.schedule_versions import resolve_schedule_version
from app.utils.departments import merge_department

router = APIRouter(prefix="/api/io", tags=["导入导出"])


@router.get("/template/{entity_type}", summary="下载CSV导入模板")
def download_template(entity_type: str):
    """下载指定实体类型的CSV导入模板"""
    content = generate_csv_template(entity_type)
    if not content:
        raise HTTPException(status_code=400, detail=f"未知的实体类型: {entity_type}")

    return StreamingResponse(
        io.BytesIO(content.encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={entity_type}_template.csv"}
    )


@router.post("/csv/{entity_type}", summary="CSV批量导入")
async def import_csv(entity_type: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """通过CSV文件批量导入实体数据"""
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="请上传CSV格式的文件")

    content = await file.read()
    try:
        text_content = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text_content = content.decode('gbk')

    # 课程大纲使用动态列解析器
    if entity_type == "syllabus":
        data_rows, parse_errors = parse_syllabus_csv(text_content)
        if parse_errors and not data_rows:
            return {"success": False, "errors": parse_errors, "imported": 0}
        return _import_syllabus(data_rows, db)

    data_rows, parse_errors = parse_csv_content(text_content, entity_type)

    if parse_errors and not data_rows:
        return {"success": False, "errors": parse_errors, "imported": 0}

    # 数据校验
    validator = ValidationService(db)
    validation_result = validator.validate_batch(entity_type, data_rows)

    if validation_result["invalid"] > 0:
        return {
            "success": False,
            "imported": 0,
            "errors": [e["message"] for e in validation_result["errors"]],
            "warnings": [w["message"] for w in validation_result["warnings"]],
            "summary": validation_result["summary"],
        }

    # 批量存入数据库
    model_map = {
        "classes": ClassInfo,
        "teachers": Teacher,
        "courses": Course,
        "classrooms": Classroom,
    }
    model_class = model_map.get(entity_type)
    if not model_class:
        raise HTTPException(status_code=400, detail=f"未知实体类型: {entity_type}")

    # 按文件顺序保留首条可导入记录，重复行不覆盖数据库或占用新值。
    labels = {"name": "名称", "teacher_code": "教师工号",
              "course_code": "课程编码", "room_code": "教室编号"}
    unique_columns = [column for column in model_class.__table__.columns if column.unique]
    seen = {column.name: {} for column in unique_columns}
    pending_rows = []
    skipped_reasons = []
    for row_number, row in enumerate(data_rows, start=2):
        reasons = []
        for column in unique_columns:
            value = row.get(column.name)
            if value is None:
                continue
            label = labels.get(column.name, column.name)
            previous = seen[column.name].get(value)
            if previous is not None:
                reasons.append(f"{label}“{value}”与本文件第{previous}行重复")
            elif db.query(model_class.id).filter(getattr(model_class, column.name) == value).first():
                reasons.append(f"{label}“{value}”已存在")
        if reasons:
            skipped_reasons.append(f"第{row_number}行已跳过：{'；'.join(reasons)}")
            continue
        pending_rows.append(row)
        for column in unique_columns:
            if row.get(column.name) is not None:
                seen[column.name][row[column.name]] = row_number

    if entity_type == 'courses':
        # Resolve only rows that will be inserted; duplicate courses remain untouched.
        import csv
        raw_rows=list(csv.DictReader(io.StringIO(text_content)))
        row_numbers=[]
        for number, raw in enumerate(raw_rows,start=2):
            code=raw.get('课程编码',raw.get('course_code',''))
            row_numbers.append((str(code or '').strip(),number))
        leader_errors=[]
        for row in pending_rows:
            code=row.pop('leader_teacher_code',None)
            if not code:continue
            teacher=db.query(Teacher).filter_by(teacher_code=code).first()
            if teacher is None:
                number=next((n for course_code,n in row_numbers if course_code==row['course_code']), '?')
                leader_errors.append(f'第{number}行: 课程负责人工号“{code}”不存在，请先导入教师')
            else:row['leader_teacher_id']=teacher.id
        if leader_errors:
            return {'success':False,'imported':0,'skipped':len(skipped_reasons),'total':len(data_rows),
                    'errors':leader_errors,'warnings':skipped_reasons,
                    'summary':f"课程负责人校验未通过，本次未导入任何记录（共{len(data_rows)}条，跳过{len(skipped_reasons)}条重复记录）"}

    imported_count = 0
    import_errors = []
    for row in pending_rows:
        try:
            obj = model_class(**row)
            db.add(obj)
            imported_count += 1
        except Exception as e:
            import_errors.append(str(e))

    accounts_created = 0
    try:
        db.flush()
        if entity_type == 'teachers':
            from app.services.teacher_accounts import provision_teacher_account
            for row in data_rows:
                teacher = db.query(Teacher).filter_by(teacher_code=row['teacher_code']).first()
                if teacher and teacher.name == row['name']:
                    accounts_created += int(provision_teacher_account(db, teacher))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="导入数据存在名称、编号或必填字段冲突，本次未写入；请核对文件并刷新现有数据后重试，无需删除排课记录")

    return {
        "success": len(import_errors) == 0,
        "imported": imported_count,
        "skipped": len(skipped_reasons),
        "accounts_created": accounts_created,
        "total": len(data_rows),
        "errors": import_errors + [e["message"] for e in parse_errors if isinstance(e, dict)],
        "warnings": skipped_reasons + [w["message"] for w in validation_result.get("warnings", [])],
        "summary": f"成功导入{imported_count}条记录，跳过{len(skipped_reasons)}条重复记录（已有数据未覆盖）" + (f"，创建{accounts_created}个工号账号" if entity_type == "teachers" else "") + (f"，{len(import_errors)}条失败" if import_errors else ""),
    }


@router.get("/export/excel", summary="导出Excel课表")
def export_excel(version: str = Query(None), db: Session = Depends(get_db)):
    """导出排课方案为Excel文件（未指定版本时导出最新版本）"""
    version = resolve_schedule_version(db, version)
    query = db.query(ScheduleEntry)
    if version:
        query = query.filter(ScheduleEntry.schedule_version == version)

    entries = query.all()
    if not entries:
        raise HTTPException(status_code=404, detail="未找到排课数据")

    entry_dicts = []
    for entry in entries:
        course = db.query(Course).filter(Course.id == entry.course_id).first()
        teacher = db.query(Teacher).filter(Teacher.id == entry.teacher_id).first()
        cls = db.query(ClassInfo).filter(ClassInfo.id == entry.class_id).first()
        room = db.query(Classroom).filter(Classroom.id == entry.classroom_id).first()

        entry_dicts.append({
            "course_name": course.name if course else "",
            "teacher_name": teacher.name if teacher else "",
            "class_name": cls.name if cls else "",
            "classroom_name": room.name if room else "",
            "week_number": entry.week_number,
            "day_of_week": entry.day_of_week,
            "period_start": entry.period_start,
            "period_end": entry.period_end,
            "is_consecutive": entry.period_end > entry.period_start,
            "status": entry.status,
        })

    metadata = {
        "version": version or entries[0].schedule_version,
        "total_entries": len(entries),
        "generated_at": "",
    }
    excel_bytes = ExportService.export_to_excel(entry_dicts, metadata)

    filename_base = f"排课方案_{version or 'latest'}"
    filename_ascii = f"scheduling_{version or 'latest'}.xlsx"
    filename_utf8 = f"{filename_base}.xlsx"
    encoded_filename = quote(filename_utf8)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename_ascii}\"; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/export/pdf", summary="导出PDF课表")
def export_pdf(version: str = Query(None), view_type: str = Query("class"),
               db: Session = Depends(get_db)):
    """导出排课方案为PDF格式（未指定版本时导出最新版本）"""
    version = resolve_schedule_version(db, version)
    query = db.query(ScheduleEntry)
    if version:
        query = query.filter(ScheduleEntry.schedule_version == version)

    entries = query.all()
    if not entries:
        raise HTTPException(status_code=404, detail="未找到排课数据")

    entry_dicts = []
    for entry in entries:
        course = db.query(Course).filter(Course.id == entry.course_id).first()
        teacher = db.query(Teacher).filter(Teacher.id == entry.teacher_id).first()
        cls = db.query(ClassInfo).filter(ClassInfo.id == entry.class_id).first()
        room = db.query(Classroom).filter(Classroom.id == entry.classroom_id).first()

        entry_dicts.append({
            "course_name": course.name if course else "",
            "teacher_name": teacher.name if teacher else "",
            "class_name": cls.name if cls else "",
            "classroom_name": room.name if room else "",
            "week_number": entry.week_number,
            "day_of_week": entry.day_of_week,
            "period_start": entry.period_start,
            "period_end": entry.period_end,
            "is_consecutive": entry.period_end > entry.period_start,
        })

    metadata = {"version": version or entries[0].schedule_version, "total_entries": len(entries)}
    pdf_bytes = ExportService.export_to_pdf(entry_dicts, metadata, view_type)

    filename_view = {"class": "班级", "teacher": "教师", "classroom": "教室"}.get(view_type, view_type)
    filename_base = f"排课方案_{filename_view}视图"
    filename_ascii = f"scheduling_{view_type}.pdf"
    filename_utf8 = f"{filename_base}.pdf"
    encoded_filename = quote(filename_utf8)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename_ascii}\"; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/report", summary="生成智能分析报告")
def generate_report(version: str = Query(None), db: Session = Depends(get_db)):
    """生成排课方案的智能分析报告（未指定版本时使用最新版本）"""
    version = resolve_schedule_version(db, version)
    query = db.query(ScheduleEntry)
    if version:
        query = query.filter(ScheduleEntry.schedule_version == version)

    entries = query.all()
    if not entries:
        raise HTTPException(status_code=404, detail="未找到排课数据")

    entry_dicts = []
    for entry in entries:
        course = db.query(Course).filter(Course.id == entry.course_id).first()
        teacher = db.query(Teacher).filter(Teacher.id == entry.teacher_id).first()
        cls = db.query(ClassInfo).filter(ClassInfo.id == entry.class_id).first()
        room = db.query(Classroom).filter(Classroom.id == entry.classroom_id).first()
        entry_dicts.append({
            "id": entry.id, "course_id": entry.course_id, "teacher_id": entry.teacher_id,
            "class_id": entry.class_id, "classroom_id": entry.classroom_id,
            "week_number": entry.week_number, "day_of_week": entry.day_of_week,
            "period_start": entry.period_start, "period_end": entry.period_end,
            "course_name": course.name if course else "",
            "teacher_name": teacher.name if teacher else "",
            "class_name": cls.name if cls else "",
            "classroom_name": room.name if room else "",
            "student_count": cls.student_count if cls else 0,
            "room_capacity": room.capacity if room else 0,
            "requires_consecutive": course.requires_consecutive if course else False,
            "preferred_time_slots": teacher.preferred_time_slots if teacher else None,
        })

    # 冲突检测
    detector = ConflictDetector(entry_dicts)
    hard, soft, stats = detector.detect_all()

    quality_score = max(0.0, 100.0 - len(hard) * 10.0 - len(soft) * 0.5)

    # AI解释
    explainer = ExplanationGenerator()
    schedule_result = {
        "version": version or entries[0].schedule_version,
        "total_entries": len(entries),
        "quality_score": round(quality_score, 1),
        "hard_conflicts": len(hard),
        "soft_conflicts": len(soft),
        "execution_time": 0,
        "entries": entry_dicts,
    }
    explanation = explainer.generate(schedule_result, conflicts={
        "hard_conflicts": hard, "soft_conflicts": soft, "conflict_stats": stats
    })

    # 生成完整报告
    report = ExportService.generate_analysis_report(
        schedule_result,
        {"hard_conflicts": hard, "soft_conflicts": soft, "conflict_stats": stats},
        explanation,
    )

    return report


def _import_syllabus(data_rows: list, db: Session) -> dict:
    """导入课程大纲：一体化创建/更新班级和课程，自动按所属专业匹配

    大纲CSV的每一行定义了「某班级上某课程，每周N课时」。
    导入逻辑：
    - 班级按名称去重：已存在则更新学生人数，不存在则新建
    - 课程按编码去重：已存在则更新周课时/专业，不存在则新建
    - 课程的 department 自动设为班级的 department，确保排课时匹配
    """
    classes_created = 0
    classes_updated = 0
    courses_created = 0
    courses_updated = 0
    errors = []

    for i, row in enumerate(data_rows, start=2):
        try:
            class_name = str(row.get("class_name", "")).strip()
            class_grade = str(row.get("class_grade", "大一")).strip()
            department = str(row.get("department", "")).strip()
            student_count = row.get("student_count")
            if student_count is not None:
                student_count = int(student_count) if str(student_count).isdigit() else None

            course_name = str(row.get("course_name", "")).strip()
            course_code = str(row.get("course_code", "")).strip()
            semester_sessions = int(row.get("semester_sessions", 16))
            weekly_sessions = int(row.get("weekly_sessions", 1))
            hours_per_session = int(row.get("hours_per_session", 2))
            total_hours = row.get("total_hours")
            if total_hours is not None:
                total_hours = int(total_hours) if str(total_hours).isdigit() else None
            credits = row.get("credits")
            if credits is not None:
                credits = int(credits) if str(credits).isdigit() else None
            course_type = str(row.get("course_type", "必修")).strip()
            requires_consecutive = row.get("requires_consecutive", False)
            if isinstance(requires_consecutive, str):
                requires_consecutive = requires_consecutive.lower() in ("yes", "true", "是", "1")
            requires_lab = row.get("requires_lab", False)
            if isinstance(requires_lab, str):
                requires_lab = requires_lab.lower() in ("yes", "true", "是", "1")
            priority = row.get("priority", 0)
            if priority is not None:
                priority = int(priority) if str(priority).isdigit() else 0

            if not class_name or not course_name or not course_code:
                errors.append(f"第{i}行: 班级名称/课程名称/课程编码不能为空")
                continue

            # 查找或创建班级
            existing_class = db.query(ClassInfo).filter(ClassInfo.name == class_name).first()
            if existing_class:
                existing_class.grade = class_grade
                if department:
                    existing_class.department = department
                if student_count is not None:
                    existing_class.student_count = student_count
                classes_updated += 1
                class_obj = existing_class
            else:
                class_obj = ClassInfo(
                    name=class_name, grade=class_grade,
                    department=department or None,
                    student_count=student_count or 0,
                )
                db.add(class_obj)
                db.flush()
                classes_created += 1

            # 查找或创建课程（department 与班级保持一致）
            existing_course = db.query(Course).filter(Course.course_code == course_code).first()
            if existing_course:
                existing_course.name = course_name
                existing_course.semester_sessions = semester_sessions
                existing_course.weekly_sessions = weekly_sessions
                existing_course.hours_per_session = hours_per_session
                existing_course.course_type = course_type
                # 共享课程可能被多个专业使用：合并专业归属，而不是用最后一行覆盖
                if department:
                    existing_course.department = merge_department(
                        existing_course.department, department)
                if total_hours is not None:
                    existing_course.total_hours = total_hours
                if credits is not None:
                    existing_course.credits = credits
                existing_course.requires_consecutive = bool(requires_consecutive)
                existing_course.requires_lab = bool(requires_lab)
                existing_course.priority = priority
                courses_updated += 1
            else:
                course_obj = Course(
                    name=course_name, course_code=course_code,
                    course_type=course_type, semester_sessions=semester_sessions,
                    weekly_sessions=weekly_sessions, hours_per_session=hours_per_session,
                    total_hours=total_hours, credits=credits or 2,
                    requires_consecutive=bool(requires_consecutive),
                    requires_lab=bool(requires_lab),
                    priority=priority, department=department or None,
                )
                db.add(course_obj)
                db.flush()
                courses_created += 1

        except Exception as e:
            errors.append(f"第{i}行处理失败: {str(e)}")

    db.commit()

    return {
        "success": len(errors) == 0,
        "imported": len(data_rows),
        "errors": errors,
        "summary": (
            f"大纲导入完成：新建班级 {classes_created} 个、更新班级 {classes_updated} 个，"
            f"新建课程 {courses_created} 门、更新课程 {courses_updated} 门"
        ),
    }
