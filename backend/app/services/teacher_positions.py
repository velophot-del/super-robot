"""Administrator-controlled appointments contribute scoped, revocable review access."""
REVIEW_POSITIONS = {'教研室主任', '教研室副主任'}


def position_grants(teacher):
    if teacher and teacher.position in REVIEW_POSITIONS and (teacher.review_major or '').strip():
        return [{'capability': 'lead', 'scope': 'dept', 'scope_id': teacher.review_major.strip()}]
    return []


def validate_position(position, review_major):
    from fastapi import HTTPException
    if position in REVIEW_POSITIONS and not (review_major or '').strip():
        raise HTTPException(status_code=422, detail='主任、副主任必须设置审核专业方向')
