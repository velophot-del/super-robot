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


@router.get('/planning-timetable')
def planning_timetable(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """合并本人已发布快照，旧课表仅提供本人历史版本；不回退冒充当前学期。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.models.planning import PublishedPlan
    from app.services.authorization import can

    teacher_id = getattr(user, 'teacher_id', None)
    if teacher_id is None or not can(user, 'teaching', {'teacher_id': teacher_id}):
        raise HTTPException(403, '此入口仅供已绑定教师身份使用')
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    first_year = today.year if today.month >= 8 else today.year - 1
    current = {'academic_year': f'{first_year}—{first_year + 1}',
               'academic_term': 2 if 2 <= today.month <= 7 else 1}
    latest = {}
    for row in db.query(PublishedPlan).order_by(PublishedPlan.id):
        latest[row.plan_id] = row
    batches = []
    for row in latest.values():
        tasks = [t for t in row.payload['tasks'] if teacher_id in t.get('teacher_ids', [])]
        if not tasks:
            continue
        plan = dict(row.payload['plan'])
        start = datetime.fromisoformat(plan['start_date']).date()
        first = start.year if start.month >= 8 else start.year - 1
        plan.setdefault('academic_year', f'{first}—{first + 1}')
        from app.services.academic_scope import plan_term
        plan.setdefault('academic_term', plan_term(plan))
        batches.append({'plan': plan, 'tasks': tasks, 'snapshot_id': row.id})
    versions = db.query(ScheduleEntry.schedule_version).filter(
        ScheduleEntry.teacher_id == teacher_id,
        ScheduleEntry.schedule_version.isnot(None)).distinct().order_by(
        ScheduleEntry.schedule_version.desc()).all()
    return {'current_period': current, 'batches': batches,
            'legacy_versions': [version for (version,) in versions]}


@router.get('/plans/{plan_id}/export')
def export_personal_plan(plan_id:int,user:User=Depends(require_user),db:Session=Depends(get_db)):
    from app.services.authorization import can
    from app.api.planning import build_plan_excel
    teacher_id=getattr(user,'teacher_id',None)
    if teacher_id is None or not can(user,'teaching',{'teacher_id':teacher_id}):
        raise HTTPException(403,'此入口仅供已绑定教师身份使用')
    return build_plan_excel(plan_id,user,db,personal_teacher_id=teacher_id)
