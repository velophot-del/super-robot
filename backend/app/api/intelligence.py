"""AI 智能辅助接口：导入清洗、自然语言问答、教师选课推荐。"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.planning import AcademicPlan
from app.services import course_recommendation, import_intelligence, qa_snapshot
from app.services.auth import require_user
from app.services.authorization import can, check
from app.utils.csv_parser import parse_csv_content

router = APIRouter(prefix='/api/intelligence', tags=['AI 智能辅助'])


class ImportReviewInput(BaseModel):
    entity_type: str = Field(pattern='^(course|teacher)$')
    records: list[dict]


class QAInput(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post('/import/review')
def import_review(data: ImportReviewInput, user=Depends(require_user), db: Session = Depends(get_db)):
    """批量导入前的智能清洗：识别疑似重复（同课异名/同名教师）与格式问题。"""
    check(user, 'admin')
    try:
        return import_intelligence.review_batch(db, data.entity_type, data.records)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post('/import/review-file')
async def import_review_file(entity_type: str = Form(...), file: UploadFile = File(...),
                             user=Depends(require_user), db: Session = Depends(get_db)):
    """上传 CSV 文件做导入前智能清洗（课程或教师）。"""
    check(user, 'admin')
    if entity_type not in ('course', 'teacher'):
        raise HTTPException(422, '仅支持课程或教师清洗')
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(400, '请上传 CSV 文件')
    content = await file.read()
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = content.decode('gbk')
    csv_type = 'courses' if entity_type == 'course' else 'teachers'
    data_rows, parse_errors = parse_csv_content(text, csv_type)
    records = []
    for row in data_rows:
        if entity_type == 'course':
            records.append({'name': row.get('name'), 'code': row.get('course_code'),
                            'department': row.get('department'), 'semester': row.get('semester'),
                            'credits': row.get('credits'), 'required_hours': row.get('total_hours')})
        else:
            records.append({'name': row.get('name'), 'teacher_code': row.get('teacher_code'),
                            'department': row.get('department'), 'email': row.get('email'),
                            'phone': row.get('phone'), 'title': row.get('title')})
    review = import_intelligence.review_batch(db, entity_type, records)
    return {'records_count': len(records), 'parse_errors': parse_errors, 'review': review}


@router.post('/qa')
def qa(data: QAInput, user=Depends(require_user), db: Session = Depends(get_db)):
    """自然语言问答：基于系统数据快照回答管理问题。"""
    if not (can(user, 'admin') or can(user, 'review') or can(user, 'publish')):
        raise HTTPException(403, '仅管理员或审核人可提问')
    return qa_snapshot.answer_question(db, data.question)


@router.post('/my-qa')
def my_qa(data: QAInput, user=Depends(require_user), db: Session = Depends(get_db)):
    """教师端问答：基于本人画像、开放周期课程与推荐回答。"""
    teacher_id = getattr(user, 'teacher_id', None)
    if teacher_id is None:
        raise HTTPException(403, '账号未绑定教师')
    check(user, 'teaching', {'teacher_id': teacher_id})
    return qa_snapshot.answer_teacher_question(db, teacher_id, data.question)


@router.get('/plans/{plan_id}/recommend')
def recommend(plan_id: int, user=Depends(require_user), db: Session = Depends(get_db)):
    """教师选课智能推荐：按本人画像为周期内课程打分并给出理由。"""
    teacher_id = getattr(user, 'teacher_id', None)
    if teacher_id is None:
        raise HTTPException(403, '账号未绑定教师')
    check(user, 'teaching', {'teacher_id': teacher_id})
    plan = db.get(AcademicPlan, plan_id)
    if plan is None:
        raise HTTPException(404, '排课周期不存在')
    return course_recommendation.recommend_with_ai(db, plan, teacher_id)
