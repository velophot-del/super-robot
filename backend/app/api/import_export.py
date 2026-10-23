"""数据导入导出API"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
import io
import hashlib
import secrets
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from urllib.parse import quote

from app.database import get_db
from app.models.class_info import ClassInfo
from app.models.teacher import Teacher
from app.models.course import Course
from app.models.classroom import Classroom
from app.models.schedule import ScheduleEntry
from app.models.planning import AcademicProgram, OfferingUnit, ImportPreviewBatch, PlanningEvent
from app.utils.csv_parser import parse_csv_content, generate_csv_template
from app.services.validation import ValidationService
from app.services.export_service import ExportService
from app.services.conflict import ConflictDetector
from app.services.explanation import ExplanationGenerator
from app.services.schedule_versions import resolve_schedule_version
from app.services.auth import require_user

router = APIRouter(prefix="/api/io", tags=["导入导出"])


class XlsxConfirmInput(BaseModel):
    preview_id: int = Field(ge=1)
    token: str = Field(min_length=20, max_length=100)


@router.post('/xlsx/courses/preview', summary='预览课程 XLSX 导入')
async def preview_courses_xlsx(file:UploadFile=File(...),user=Depends(require_user),db:Session=Depends(get_db)):
    from app.services.authorization import check
    from app.services.spreadsheet_import import parse_course_workbook,course_row_issues,normalize_course_row
    check(user,'admin')
    if not file.filename or not file.filename.lower().endswith('.xlsx'):
        raise HTTPException(400,'请上传.xlsx格式的课程文件')
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024:raise HTTPException(413,'文件不能超过10MB')
    try:rows,parse_errors=parse_course_workbook(content)
    except Exception as exc:raise HTTPException(422,f'Excel解析失败：{exc}') from exc
    if not rows and not parse_errors:raise HTTPException(422,'Excel中没有可识别的课程数据')
    seen=set();preview_rows=[];counts={'new':0,'duplicate':0,'invalid':0}
    for row in rows:
        issues,teacher_id,unit_id=course_row_issues(row,db)
        code=str(row.get('course_code') or '').strip()
        if code and (code in seen or db.query(Course.id).filter_by(course_code=code).first()):
            if not issues:status='duplicate'
            else:status='invalid'
        elif issues:status='invalid'
        else:status='new'
        if code:seen.add(code)
        counts[status]+=1
        data=normalize_course_row(row,teacher_id,unit_id)
        preview_rows.append({'source_sheet':row['_source_sheet'],'source_row':row['_source_row'],
            'course_code':code,'name':row.get('name'),'status':status,'issues':issues,'data':data})
    token=secrets.token_urlsafe(32)
    batch=ImportPreviewBatch(entity_type='courses',filename=file.filename[:200],
        file_sha256=hashlib.sha256(content).hexdigest(),token_hash=hashlib.sha256(token.encode()).hexdigest(),
        status='pending',payload={'rows':preview_rows,'counts':counts,'parse_errors':parse_errors},
        expires_at=datetime.utcnow()+timedelta(minutes=30))
    db.add(batch);db.commit();db.refresh(batch)
    return {'preview_id':batch.id,'token':token,'expires_at':batch.expires_at,'counts':counts,
            'rows':preview_rows,'parse_errors':parse_errors,'file_sha256':batch.file_sha256}


@router.post('/xlsx/courses/confirm', summary='确认导入课程 XLSX')
def confirm_courses_xlsx(data:XlsxConfirmInput,user=Depends(require_user),db:Session=Depends(get_db)):
    from app.services.authorization import check
    from app.services.spreadsheet_import import normalize_course_row
    from app.api.planning import write
    check(user,'admin')
    batch=db.get(ImportPreviewBatch,data.preview_id)
    supplied=hashlib.sha256(data.token.encode()).hexdigest()
    if not batch or batch.entity_type!='courses' or not secrets.compare_digest(batch.token_hash,supplied):
        raise HTTPException(404,'导入预览不存在或令牌无效')
    if batch.status!='pending':raise HTTPException(409,'该导入预览已确认或失效')
    if batch.expires_at<datetime.utcnow():raise HTTPException(409,'导入预览已过期，请重新上传')
    with write(db):
        payload=dict(batch.payload);imported=0;skipped=0
        for row in payload['rows']:
            if row['status']!='new':skipped+=1;continue
            if db.query(Course.id).filter_by(course_code=row['course_code']).first():
                skipped+=1;continue
            db.add(Course(**row['data']));imported+=1
        batch.status='confirmed'
        result={'imported':imported,'skipped':skipped,'file_sha256':batch.file_sha256}
        payload['result']=result;batch.payload=payload
        db.add(PlanningEvent(plan_id=None,actor=f"{'demo' if getattr(user,'is_demo',False) else 'user'}:{user.id}",
            action='import_courses_xlsx',payload=result))
    return {'success':True,**result,'summary':f'成功导入{imported}门课程，跳过重复或无效记录{skipped}条'}


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


@router.get('/template/courses/xlsx', summary='下载课程 Excel 导入模板')
def download_course_xlsx_template():
    from openpyxl import Workbook
    rows=list(__import__('csv').reader(io.StringIO(generate_csv_template('courses'))))
    workbook=Workbook();sheet=workbook.active;sheet.title='课程数据'
    for row in rows:sheet.append(row)
    output=io.BytesIO();workbook.save(output);output.seek(0)
    return StreamingResponse(output,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':'attachment; filename="courses_template.xlsx"'})


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

    if entity_type == "syllabus":
        raise HTTPException(status_code=410, detail='课程一体化导入已停用，请通过课程管理导入课程数据')

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

    scope_errors=[]
    if entity_type=='classes':
        for row in pending_rows:
            code=(row.pop('program_code',None) or '').strip()
            program=db.query(AcademicProgram).filter_by(code=code).first() if code else None
            if code and not program:
                scope_errors.append(f"班级“{row.get('name')}”的专业编码“{code}”不存在")
            elif program and row.get('department') and row['department'].strip()!=program.name:
                scope_errors.append(f"班级“{row.get('name')}”的专业名称与编码{code}不一致")
            elif program:
                row['program_id']=program.id
            elif row.get('department'):
                exact=db.query(AcademicProgram).filter_by(name=row['department'].strip()).first()
                if exact:row['program_id']=exact.id
    elif entity_type=='courses':
        for row in pending_rows:
            code=(row.pop('offering_unit_code',None) or '').strip()
            unit=db.query(OfferingUnit).filter_by(code=code).first() if code else None
            if code and not unit:scope_errors.append(f"课程“{row.get('name')}”的开课单位编码“{code}”不存在")
            elif unit:row['offering_unit_id']=unit.id
    if scope_errors:
        return {'success':False,'imported':0,'skipped':len(skipped_reasons),'total':len(data_rows),
                'errors':scope_errors,'warnings':skipped_reasons,
                'summary':'专业或开课单位编码校验未通过，本次未导入任何记录'}

    if entity_type == 'courses':
        # Resolve only rows that will be inserted; duplicate courses remain untouched.
        from app.services.course_library import normalize_course_classification
        for row in pending_rows:
            row['course_type'],row['course_nature']=normalize_course_classification(
                row.get('course_type'),row.get('course_nature'))
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
