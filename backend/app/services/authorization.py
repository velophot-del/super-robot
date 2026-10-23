from fastapi import Depends, HTTPException


def can(user, action: str, resource: dict | None = None) -> bool:
    resource = resource or {}
    for grant in getattr(user, 'grants', []):
        capability = grant['capability']
        # 教研室主任只获得其授权专业方向内的审核权，不继承管理员或发布职能。
        if capability != action and not (action == 'review' and capability == 'lead'):
            continue
        if capability == 'lead' and grant.get('scope') != 'dept':
            continue
        if grant['scope'] == 'all':
            return True
        if (grant['scope'] == 'self' and getattr(user, 'teacher_id', None) is not None
                and resource.get('teacher_id') == user.teacher_id):
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
