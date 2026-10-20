"""约束规则管理API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, List

from app.database import get_db
from app.models.constraint import ConstraintRule
from app.models.schedule import ScheduleEntry
from app.models.course import Course
from app.models.teacher import Teacher
from app.models.class_info import ClassInfo
from app.models.classroom import Classroom
from app.schemas.constraint import (
    ConstraintRuleCreate, ConstraintRuleUpdate,
    ConstraintRuleResponse, ConstraintLearningResult
)
from app.services.conflict import ConflictDetector
from app.services.optimization import ConstraintLearningService

router = APIRouter(prefix="/api/constraints", tags=["约束管理"])


def _constraint_dict(rule: ConstraintRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "category": rule.category,
        "rule_expression": rule.rule_expression,
        "weight": rule.weight,
        "penalty_score": rule.penalty_score,
        "priority": rule.priority,
        "is_active": rule.is_active,
    }


def _version_entry_dicts(db: Session, entries: List[ScheduleEntry]) -> List[dict]:
    """把数据库中的排课条目转换为约束评估所需的完整字典。"""
    courses = {c.id: c for c in db.query(Course).all()}
    teachers = {t.id: t for t in db.query(Teacher).all()}
    classes = {c.id: c for c in db.query(ClassInfo).all()}
    classrooms = {r.id: r for r in db.query(Classroom).all()}

    result = []
    for entry in entries:
        course = courses.get(entry.course_id)
        teacher = teachers.get(entry.teacher_id)
        class_info = classes.get(entry.class_id)
        classroom = classrooms.get(entry.classroom_id)
        result.append({
            "id": entry.id,
            "course_id": entry.course_id,
            "teacher_id": entry.teacher_id,
            "class_id": entry.class_id,
            "classroom_id": entry.classroom_id,
            "week_number": entry.week_number,
            "day_of_week": entry.day_of_week,
            "period_start": entry.period_start,
            "period_end": entry.period_end,
            "course_name": course.name if course else "",
            "teacher_name": teacher.name if teacher else "",
            "class_name": class_info.name if class_info else "",
            "classroom_name": classroom.name if classroom else "",
            "student_count": class_info.student_count if class_info else 0,
            "room_capacity": classroom.capacity if classroom else 0,
            "requires_consecutive": course.requires_consecutive if course else False,
            "preferred_time_slots": teacher.preferred_time_slots if teacher else None,
        })
    return result


@router.get("/", response_model=List[ConstraintRuleResponse], summary="获取约束规则列表")
def list_constraints(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    rule_type: str = Query(None, description="hard/soft"),
    category: str = Query(None),
    is_active: bool = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(ConstraintRule)
    if rule_type:
        query = query.filter(ConstraintRule.rule_type == rule_type)
    if category:
        query = query.filter(ConstraintRule.category == category)
    if is_active is not None:
        query = query.filter(ConstraintRule.is_active == is_active)
    return query.order_by(ConstraintRule.priority.desc()).offset(skip).limit(limit).all()


@router.get("/defaults", summary="获取默认约束规则")
def get_default_constraints():
    """获取系统预置的默认约束规则"""
    defaults = [
        {"name": "教师时间不冲突", "rule_type": "hard", "category": "teacher",
         "description": "同一教师在同一时间只能教授一门课程",
         "weight": 10.0, "penalty_score": 100.0, "priority": 10,
         "rule_expression": '{"type": "unique", "fields": ["teacher_id", "day_of_week", "period_start"]}'},

        {"name": "教室不重复占用", "rule_type": "hard", "category": "classroom",
         "description": "同一教室在同一时间只能被一个班级使用",
         "weight": 10.0, "penalty_score": 100.0, "priority": 10,
         "rule_expression": '{"type": "unique", "fields": ["classroom_id", "day_of_week", "period_start"]}'},

        {"name": "班级课程不冲突", "rule_type": "hard", "category": "class",
         "description": "同一班级在同一时间只能上一门课程",
         "weight": 10.0, "penalty_score": 100.0, "priority": 10,
         "rule_expression": '{"type": "unique", "fields": ["class_id", "day_of_week", "period_start"]}'},

        {"name": "教室容量匹配", "rule_type": "hard", "category": "classroom",
         "description": "教室容量应不小于上课班级的学生人数",
         "weight": 8.0, "penalty_score": 50.0, "priority": 8,
         "rule_expression": '{"type": "compare", "field1": "room_capacity", "field2": "student_count", "op": "gte"}'},

        {"name": "教师时间偏好", "rule_type": "soft", "category": "teacher",
         "description": "尽量满足教师的时间偏好设置",
         "weight": 5.0, "penalty_score": 5.0, "priority": 5,
         "rule_expression": '{"type": "preference", "field": "preferred_time_slots"}'},

        {"name": "课时均匀分布", "rule_type": "soft", "category": "time",
         "description": "同一课程在一周内应尽量均匀分布，避免集中在某一天",
         "weight": 4.0, "penalty_score": 3.0, "priority": 4,
         "rule_expression": '{"type": "distribution", "max_per_day": 2}'},

        {"name": "连排课程要求", "rule_type": "soft", "category": "course",
         "description": "需要连排的课程应安排在连续的两个节次",
         "weight": 6.0, "penalty_score": 8.0, "priority": 6,
         "rule_expression": '{"type": "consecutive", "min_gap": 0}'},

        {"name": "班级日课时均衡", "rule_type": "soft", "category": "class",
         "description": "每个班级每日的课时数应尽量均衡",
         "weight": 3.0, "penalty_score": 2.0, "priority": 3,
         "rule_expression": '{"type": "balance", "field": "class_id", "group_by": "day_of_week"}'},
    ]
    return {"defaults": defaults}


@router.get("/{rule_id}", response_model=ConstraintRuleResponse, summary="获取约束详情")
def get_constraint(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ConstraintRule).filter(ConstraintRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="约束规则不存在")
    return rule


@router.post("/", response_model=ConstraintRuleResponse, status_code=201, summary="创建约束规则")
def create_constraint(data: ConstraintRuleCreate, db: Session = Depends(get_db)):
    rule = ConstraintRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=ConstraintRuleResponse, summary="更新约束规则")
def update_constraint(rule_id: int, data: ConstraintRuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(ConstraintRule).filter(ConstraintRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="约束规则不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204, summary="删除约束规则")
def delete_constraint(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ConstraintRule).filter(ConstraintRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="约束规则不存在")
    db.delete(rule)
    db.commit()


@router.post("/learn", response_model=List[ConstraintLearningResult], summary="执行约束自学习")
def learn_constraints(db: Session = Depends(get_db)):
    """基于真实历史排课版本执行约束自学习分析。

    每个历史版本都会按当前启用的约束规则重新评估违反次数，并据此统计满足率、
    冲突严重度和对方案质量的相关性；没有任何历史版本时不返回虚构数据。
    """
    constraints = db.query(ConstraintRule).all()
    if not constraints:
        return []

    constraint_dicts = [_constraint_dict(rule) for rule in constraints]
    name_by_id = {rule.id: rule.name for rule in constraints}

    learning_service = ConstraintLearningService()

    versions = [
        row[0]
        for row in db.query(ScheduleEntry.schedule_version)
        .filter(ScheduleEntry.schedule_version.isnot(None))
        .distinct()
        .order_by(ScheduleEntry.schedule_version.desc())
        .all()
    ]

    history: List[Dict] = []
    for version in versions:
        entries = (
            db.query(ScheduleEntry)
            .filter(ScheduleEntry.schedule_version == version)
            .all()
        )
        if not entries:
            continue

        entry_dicts = _version_entry_dicts(db, entries)
        total = max(1, len(entry_dicts))

        detector = ConflictDetector(entry_dicts)
        hard_conflicts, soft_conflicts, _stats = detector.detect_all()
        # 质量代理分：硬冲突权重更高，用于与满足率做相关性分析
        quality = max(0.0, 100.0 - len(hard_conflicts) * 10.0 - len(soft_conflicts) * 0.5)

        violations = {}
        satisfaction_rates = {}
        for rule in constraint_dicts:
            count = learning_service.count_violations(rule, entry_dicts)
            violations[str(rule["id"])] = count
            satisfaction_rates[str(rule["id"])] = max(0.0, 1.0 - count / total)

        history.append({
            "version": version,
            "quality_score": quality,
            "total_entries": total,
            "hard_violations": len(hard_conflicts),
            "soft_violations": len(soft_conflicts),
            "constraints": constraint_dicts,
            "violations": violations,
            "constraint_satisfaction_rates": satisfaction_rates,
        })

    if not history:
        return []

    learning_service.load_history(history)
    learning_results = learning_service.learn_from_history(history, constraint_dicts)

    results = []
    for impact in learning_results.get("constraint_impacts", []):
        rule_id = impact.get("rule_id")
        try:
            rule_id_int = int(rule_id)
        except (TypeError, ValueError):
            rule_id_int = 0

        results.append(ConstraintLearningResult(
            rule_id=rule_id_int,
            rule_name=impact.get("rule_name") or name_by_id.get(rule_id_int, str(rule_id or "")),
            satisfaction_rate=float(impact.get("satisfaction_rate", 0.0)),
            conflict_count=int(impact.get("conflict_count", impact.get("avg_violations", 0))),
            conflict_severity_mean=float(impact.get("conflict_severity_mean", 0.0)),
            impact_on_quality=float(impact.get("impact_on_quality", 0.0)),
            recommendation=impact.get("recommendation", ""),
        ))

    # 把学习结果写回规则，便于列表页展示历史满足率和严重度
    impacts_by_id = {result.rule_id: result for result in results}
    for rule in constraints:
        learned = impacts_by_id.get(rule.id)
        if learned:
            rule.satisfaction_rate = learned.satisfaction_rate
            rule.conflict_severity = learned.conflict_severity_mean
            rule.learned_from_history = True
    db.commit()

    return results
