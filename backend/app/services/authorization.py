from fastapi import Depends, HTTPException


def can(user, action: str, resource: dict | None = None) -> bool:
    resource = resource or {}
    for grant in getattr(user, 'grants', []):
        if grant['capability'] != action:
            continue
        if grant['scope'] == 'all':
            return True
        if grant['scope'] == 'self' and resource.get('teacher_id') == getattr(user, 'teacher_id', None):
            return True
        if grant['scope'] == 'dept' and str(resource.get('department')) == grant.get('scope_id'):
            return True
        if grant['scope'] == 'course' and str(resource.get('code')) == grant.get('scope_id'):
            return True
    return False


def check(user, action, resource=None):
    if not can(user, action, resource):
        raise HTTPException(403, '没有此项职能或超出授权范围')


def permission(action):
    from app.services.auth import require_user
    def dependency(user=Depends(require_user)):
        check(user, action, {'teacher_id': getattr(user, 'teacher_id', None)})
        return user
    return dependency
