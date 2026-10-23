"""专业与开课单位基础目录。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.planning import AcademicProgram, OfferingUnit
from app.services.auth import require_user
from app.services.authorization import check
from app.api.planning import write

router = APIRouter(prefix='/api/planning', tags=['专业与开课单位'])


class ProgramInput(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    duration_semesters: int = Field(default=8, ge=1, le=20)


class OfferingUnitInput(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)


@router.get('/programs')
def list_programs(user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    return [{'id': row.id, 'code': row.code, 'name': row.name,
             'duration_semesters': row.duration_semesters, 'is_active': row.is_active}
            for row in db.query(AcademicProgram).order_by(AcademicProgram.name)]


@router.post('/programs')
def create_program(data: ProgramInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    with write(db):
        code, name = data.code.strip(), data.name.strip()
        if db.query(AcademicProgram).filter((AcademicProgram.code == code) |
                                            (AcademicProgram.name == name)).first():
            raise HTTPException(409, '专业编码或名称已存在')
        row = AcademicProgram(code=code, name=name, duration_semesters=data.duration_semesters)
        db.add(row)
        db.flush()
        return {'id': row.id, 'code': row.code, 'name': row.name,
                'duration_semesters': row.duration_semesters, 'is_active': row.is_active}


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
