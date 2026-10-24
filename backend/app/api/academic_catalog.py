"""专业与开课单位基础目录。"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import date
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.planning import (AcademicDirection, AcademicProgram, OfferingUnit,
    AcademicPlan, TeachingTask, PlanningEvent, CohortCalendarRule)
from app.models.class_info import ClassInfo
from app.models.teacher import Teacher
from app.services.auth import require_user
from app.services.authorization import check
from app.api.planning import write
from app.services.cohort_calendar import normalize_cohort, calendar_rule_payload
from app.services.exam_weeks import exam_weeks_for

router = APIRouter(prefix='/api/planning', tags=['专业与开课单位'])


class CohortCalendarRuleInput(BaseModel):
    weeks: int = Field(ge=1, le=20)
    start_date: date
    exam_weeks: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def validate_calendar(self):
        if self.start_date.weekday() != 0:
            raise ValueError('课程开始日期必须为周一')
        if len(set(self.exam_weeks)) != len(self.exam_weeks):
            raise ValueError('考试周不能重复')
        if any(week < 1 or week > self.weeks for week in self.exam_weeks):
            raise ValueError(f'考试周必须在1—{self.weeks}周范围内')
        self.exam_weeks = sorted(self.exam_weeks)
        return self


def _legacy_calendar_suggestion(db, cohort):
    class_names = {row.name for row in db.query(ClassInfo) if normalize_cohort(row.grade) == cohort}
    for plan in db.query(AcademicPlan).order_by(AcademicPlan.id.desc()):
        settings = plan.settings or {}
        if normalize_cohort(settings.get('cohort')) == cohort or class_names.intersection(settings.get('groups') or []):
            exam_weeks = sorted(exam_weeks_for(plan, cohort, None, plan.weeks))
            return {'cohort': cohort, 'weeks': plan.weeks, 'start_date': plan.start_date.isoformat(),
                    'exam_weeks': exam_weeks, 'revision': 0, 'configured': False,
                    'source': f'兼容周期：{plan.name}'}
    return {'cohort': cohort, 'weeks': 20, 'start_date': None, 'exam_weeks': [20],
            'revision': 0, 'configured': False, 'source': '默认建议，请设置开课日期'}


@router.get('/calendar-rules')
def list_calendar_rules(user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    cohorts = {normalize_cohort(row.grade) for row in db.query(ClassInfo.grade).filter(
        ClassInfo.grade.is_not(None)).distinct() if normalize_cohort(row.grade)}
    configured = {row.cohort: row for row in db.query(CohortCalendarRule)}
    result = []
    for cohort in sorted(cohorts | set(configured)):
        row = configured.get(cohort)
        result.append(calendar_rule_payload(row) if row else _legacy_calendar_suggestion(db, cohort))
    return result


@router.put('/calendar-rules/{cohort}')
def save_calendar_rule(cohort: str, data: CohortCalendarRuleInput,
                       user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    key = normalize_cohort(cohort)
    if not key or len(key) > 20:
        raise HTTPException(422, '年级格式无效')
    with write(db):
        class_names = {row.name for row in db.query(ClassInfo) if normalize_cohort(row.grade) == key}
        conflicts = []
        for plan in db.query(AcademicPlan).filter(AcademicPlan.state != 'published'):
            for task in db.query(TeachingTask).filter_by(plan_id=plan.id):
                payload = task.payload or {}
                task_cohort = normalize_cohort(payload.get('cohort'))
                if not task_cohort and payload.get('group') in class_names:
                    task_cohort = key
                if task_cohort != key or not payload.get('start_week') or not payload.get('end_week'):
                    continue
                span = set(range(int(payload['start_week']), int(payload['end_week']) + 1))
                blocked = span & set(data.exam_weeks)
                if int(payload['end_week']) > data.weeks:
                    conflicts.append(f"{payload.get('name', '课程')}（{payload.get('group', '')}）超出{data.weeks}周")
                elif blocked:
                    conflicts.append(f"{payload.get('name', '课程')}（{payload.get('group', '')}）占用考试周{','.join(map(str, sorted(blocked)))}")
        if conflicts:
            raise HTTPException(409, '规则会与已有排课冲突，请先调整课程周段：' + '；'.join(conflicts[:10]))
        row = db.get(CohortCalendarRule, key)
        if row:
            row.weeks = data.weeks
            row.start_date = data.start_date
            row.exam_weeks = data.exam_weeks
            row.revision += 1
        else:
            row = CohortCalendarRule(cohort=key, weeks=data.weeks, start_date=data.start_date,
                                     exam_weeks=data.exam_weeks, revision=1)
            db.add(row)
        db.add(PlanningEvent(plan_id=None, actor=f"{'demo' if getattr(user, 'is_demo', False) else 'user'}:{user.id}",
            action='set_cohort_calendar_rule', payload=calendar_rule_payload(row)))
        db.flush()
        return calendar_rule_payload(row)


class ProgramInput(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    duration_semesters: int = Field(default=8, ge=1, le=20)
    education_level: str = Field(default='本科', min_length=1, max_length=20)
    degree_category: str | None = Field(None, max_length=30)
    construction_level: str | None = Field(None, max_length=300)
    source_notes: str | None = Field(None, max_length=1000)


class ProgramUpdate(BaseModel):
    duration_semesters: int | None = Field(None, ge=1, le=20)
    education_level: str | None = Field(None, min_length=1, max_length=20)
    degree_category: str | None = Field(None, max_length=30)
    construction_level: str | None = Field(None, max_length=300)
    source_notes: str | None = Field(None, max_length=1000)
    is_active: bool | None = None


class OfferingUnitInput(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)


@router.get('/programs')
def list_programs(user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    return [{'id': row.id, 'code': row.code, 'name': row.name,
             'duration_semesters': row.duration_semesters, 'education_level':row.education_level,
             'degree_category':row.degree_category,'construction_level':row.construction_level,
             'source_notes':row.source_notes,
             'direction_count':db.query(AcademicDirection.id).filter_by(program_id=row.id,entry_type='专业方向').count(),
             'is_active': row.is_active}
            for row in db.query(AcademicProgram).order_by(AcademicProgram.name)]


@router.post('/programs')
def create_program(data: ProgramInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    with write(db):
        code, name = data.code.strip(), data.name.strip()
        if db.query(AcademicProgram).filter((AcademicProgram.code == code) |
                                            (AcademicProgram.name == name)).first():
            raise HTTPException(409, '专业编码或名称已存在')
        row = AcademicProgram(code=code, name=name, duration_semesters=data.duration_semesters,
                              education_level=data.education_level,degree_category=data.degree_category,
                              construction_level=data.construction_level,source_notes=data.source_notes)
        db.add(row)
        db.flush()
        return {'id': row.id, 'code': row.code, 'name': row.name,
                'duration_semesters': row.duration_semesters,'education_level':row.education_level,
                'degree_category':row.degree_category,'construction_level':row.construction_level,
                'source_notes':row.source_notes,'is_active': row.is_active}


@router.put('/programs/{program_id}')
def update_program(program_id: int, data: ProgramUpdate,
                   user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    updates=data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(422, '请提供要修改的专业学制或启用状态')
    with write(db):
        row=db.get(AcademicProgram,program_id)
        if not row:
            raise HTTPException(404, '标准专业不存在')
        for key,value in updates.items():
            setattr(row,key,value)
        return {'id':row.id,'code':row.code,'name':row.name,
                'duration_semesters':row.duration_semesters,'education_level':row.education_level,
                'degree_category':row.degree_category,'construction_level':row.construction_level,
                'source_notes':row.source_notes,'is_active':row.is_active}


class DirectionInput(BaseModel):
    program_id: int
    name: str = Field(min_length=1, max_length=150)
    entry_type: str = Field(default='专业方向', min_length=1, max_length=30)
    offering_unit_id: int | None = None
    notes: str | None = Field(None, max_length=1000)
    source_order: int = Field(default=0, ge=0)


class DirectionUpdate(BaseModel):
    program_id: int | None = None
    name: str | None = Field(None, min_length=1, max_length=150)
    entry_type: str | None = Field(None, min_length=1, max_length=30)
    offering_unit_id: int | None = None
    notes: str | None = Field(None, max_length=1000)
    source_order: int | None = Field(None, ge=0)


def _direction_row(row: AcademicDirection, db: Session):
    program = db.get(AcademicProgram, row.program_id)
    unit = db.get(OfferingUnit, row.offering_unit_id) if row.offering_unit_id else None
    return {'id':row.id,'program_id':row.program_id,'program_code':program.code if program else '',
            'program_name':program.name if program else '', 'name':row.name,'entry_type':row.entry_type,
            'offering_unit_id':row.offering_unit_id,'offering_unit_name':unit.name if unit else None,
            'notes':row.notes,'source_order':row.source_order}


@router.get('/directions')
def list_directions(user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    rows=db.query(AcademicDirection).order_by(AcademicDirection.source_order,AcademicDirection.id).all()
    return [_direction_row(row,db) for row in rows]


@router.post('/directions')
def create_direction(data: DirectionInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user,'admin')
    if not db.get(AcademicProgram,data.program_id):
        raise HTTPException(404,'所属专业不存在')
    if data.offering_unit_id is not None and not db.get(OfferingUnit,data.offering_unit_id):
        raise HTTPException(404,'对应教研室不存在')
    with write(db):
        row=AcademicDirection(**data.model_dump())
        row.name=row.name.strip()
        db.add(row);db.flush()
        return _direction_row(row,db)


@router.put('/directions/{direction_id}')
def update_direction(direction_id:int,data:DirectionUpdate,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    updates=data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(422,'请提供要修改的方向数据')
    if updates.get('offering_unit_id') is not None and not db.get(OfferingUnit,updates['offering_unit_id']):
        raise HTTPException(404,'对应教研室不存在')
    if updates.get('program_id') is not None and not db.get(AcademicProgram,updates['program_id']):
        raise HTTPException(404,'所属专业不存在')
    with write(db):
        row=db.get(AcademicDirection,direction_id)
        if not row:
            raise HTTPException(404,'专业方向不存在')
        for key,value in updates.items():
            setattr(row,key,value.strip() if key in ('name','entry_type') and value else value)
        db.flush()
        return _direction_row(row,db)


@router.delete('/directions/{direction_id}')
def delete_direction(direction_id:int,user=Depends(require_user),db:Session=Depends(get_db)):
    check(user,'admin')
    with write(db):
        row=db.get(AcademicDirection,direction_id)
        if not row:
            raise HTTPException(404,'专业方向不存在')
        db.delete(row)
        return {'ok':True}


@router.get('/offering-units')
def list_offering_units(user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    return [{'id': row.id, 'code': row.code, 'name': row.name, 'is_active': row.is_active}
            for row in db.query(OfferingUnit).order_by(OfferingUnit.name)]


@router.post('/offering-units')
def create_offering_unit(data: OfferingUnitInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    with write(db):
        code, name = data.code.strip(), data.name.strip()
        if db.query(OfferingUnit).filter((OfferingUnit.code == code) |
                                         (OfferingUnit.name == name)).first():
            raise HTTPException(409, '开课单位编码或名称已存在')
        row = OfferingUnit(code=code, name=name)
        db.add(row)
        db.flush()
        return {'id': row.id, 'code': row.code, 'name': row.name, 'is_active': row.is_active}


class OfferingUnitRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.put('/offering-units/{unit_id}')
def rename_offering_unit(unit_id: int, data: OfferingUnitRename,
                         user=Depends(require_user), db: Session=Depends(get_db)):
    check(user, 'admin')
    name=data.name.strip()
    if not name:
        raise HTTPException(422, '教研室名称不能为空')
    with write(db):
        row=db.get(OfferingUnit, unit_id)
        if not row:
            raise HTTPException(404, '教研室不存在')
        duplicate=db.query(OfferingUnit.id).filter(OfferingUnit.name==name,OfferingUnit.id!=unit_id).first()
        if duplicate:
            raise HTTPException(409, '教研室名称已存在')
        old_name=row.name
        row.name=name
        db.query(Teacher).filter(Teacher.department==old_name).update(
            {Teacher.department:name}, synchronize_session=False)
        return {'id':row.id,'code':row.code,'name':row.name,'is_active':row.is_active}
