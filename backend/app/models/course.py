"""课程数据模型"""
from sqlalchemy import Column, Integer, Float, String, Text, Boolean, DateTime, JSON, func, ForeignKey
from app.database import Base
from app.models.base import TimestampMixin


class Course(Base, TimestampMixin):
    """课程信息"""
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="课程ID")
    name = Column(String(200), nullable=False, comment="课程名称")
    course_code = Column(String(50), unique=True, nullable=False, comment="课程编码")
    course_type = Column(String(30), default="专业课", comment="课程类型")
    course_nature = Column(String(20), nullable=False, default="必修课", comment="课程性质: 必修课/限选课/任选课")
    semester = Column(Integer, nullable=True, comment="上课学期（培养方案学期）")
    cohort = Column(String(20), nullable=True, comment="适用年级；为空时按专业和上课学期匹配")
    teaching_weeks = Column(Integer, nullable=True, comment="授课周数（来自教学计划）")
    tail_hours = Column(Integer, nullable=True, comment="尾周学时，适用于最后一周课时不同的课程")
    weekdays = Column(JSON, nullable=False, default=list,
                      comment="每周固定上课日（1=周一 … 7=周日），具体节次由排课阶段安排")
    total_hours = Column(Integer, nullable=True, comment="计划总学时")
    credits = Column(Float, nullable=True, default=2, comment="学分")
    requires_consecutive = Column(Boolean, default=False, comment="是否需要连排(连续两节)")
    requires_lab = Column(Boolean, default=False, comment="是否需要实验室/机房")
    priority = Column(Integer, default=0, comment="优先级(0-10,越大越优先)")
    department = Column(String(100), nullable=True, comment="所属专业")
    program_id = Column(Integer, ForeignKey('academic_programs.id'), nullable=True, comment='标准专业')
    direction_id = Column(Integer, ForeignKey('academic_directions.id'), nullable=True, comment='专业方向')
    offering_unit_id = Column(Integer, ForeignKey('offering_units.id'), nullable=True, comment='开课单位')
    leader_teacher_id = Column(Integer, ForeignKey('teachers.id', ondelete='SET NULL'), nullable=True, comment='课程负责人')
    remarks = Column(Text, nullable=True, comment="备注/课程描述")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否纳入课程库与新排课周期")

    def __repr__(self):
        return f"<Course(id={self.id}, name='{self.name}')>"
