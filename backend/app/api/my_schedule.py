"""教师本人课表，数据范围只从服务端身份获取。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schedules import _enrich_entry
from app.database import get_db
from app.models.schedule import ScheduleEntry
from app.models.user import User
from app.schemas.schedule import ScheduleEntryResponse
from app.services.auth import require_user

router = APIRouter(prefix="/api/my", tags=["教师工作台"])


@router.get("/timetable", response_model=list[ScheduleEntryResponse])
def my_timetable(version: str | None = None, skip: int = Query(0, ge=0),
                 limit: int = Query(500, ge=1, le=2000),
                 user: User = Depends(require_user), db: Session = Depends(get_db)):
    teacher_id = getattr(user, "teacher_id", None)
    from app.services.authorization import can
    if not can(user, 'teaching', {'teacher_id': teacher_id}) or teacher_id is None:
        raise HTTPException(status_code=403, detail="此入口仅供已绑定教师身份使用")
    if version is None:
        latest = db.query(ScheduleEntry.schedule_version).filter(
            ScheduleEntry.schedule_version.isnot(None)).order_by(
            ScheduleEntry.schedule_version.desc()).first()
        if latest is None:
            return []
        version = latest[0]
    entries = db.query(ScheduleEntry).filter(
        ScheduleEntry.teacher_id == teacher_id,
        ScheduleEntry.schedule_version == version,
    ).order_by(ScheduleEntry.week_number, ScheduleEntry.day_of_week,
               ScheduleEntry.period_start, ScheduleEntry.id).offset(skip).limit(limit).all()
    return [_enrich_entry(entry, db) for entry in entries]
