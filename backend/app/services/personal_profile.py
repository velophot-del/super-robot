"""Teacher declarations stay separate from administrator-verified records."""
from fastapi import HTTPException
from app.models.planning import TeacherProfile


def missing_profile_fields(profile):
    own=(profile or {}).get('self_profile') or {}
    missing=[]
    if not own.get('direction','').strip():missing.append('专业方向')
    if not any(str(v).strip() for v in own.get('tags',[])):missing.append('专业领域')
    if not any(str(v).strip() for v in own.get('skilled_courses',[])):missing.append('擅长课程')
    return missing


def require_personal_profile(db,teacher_id):
    record=db.get(TeacherProfile,teacher_id)
    missing=missing_profile_fields(record.payload if record else {})
    if missing:raise HTTPException(403,'请先完善个人资料：'+'、'.join(missing))


def effective_profile(payload):
    result=dict(payload)
    own=payload.get('self_profile') or {}
    if own:
        result.update(direction=own.get('direction',''),tags=own.get('tags',[]),skilled_courses=own.get('skilled_courses',[]))
    result['professional_profile_source']='self_declared' if own and not missing_profile_fields(payload) else 'admin_verified' if payload.get('verified') else 'unknown'
    return result
