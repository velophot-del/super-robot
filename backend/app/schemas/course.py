"""课程相关Pydantic模式"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime


def _clean_weekdays(value):
    if value is None:
        return []
    days = sorted({int(day) for day in value})
    if any(day < 1 or day > 7 for day in days):
        raise ValueError('每周上课日须为1至7（周一至周日）')
    return days


class CourseBase(BaseModel):
    """课程基础字段"""
    name: str = Field(..., min_length=1, max_length=200, description="课程名称")
    course_code: str = Field(..., min_length=1, max_length=50, description="课程编码")
    course_type: str = Field(default="专业课", description="课程类型")
    course_nature: str = Field(default="必修课", description="课程性质")
    semester: Optional[int] = Field(None, ge=1, le=12, description="上课学期（培养方案学期）")
    cohort: Optional[str] = Field(None, max_length=20, description="适用年级，如2026")
    teaching_weeks: Optional[int] = Field(None, ge=1, le=20, description="授课周数")
    tail_hours: Optional[int] = Field(None, ge=0, description="尾周学时")
    weekdays: list[int] = Field(default_factory=list, description="每周固定上课日（1=周一…7=周日）")
    total_hours: Optional[int] = Field(None, ge=0, description="计划总学时")
    credits: Optional[float] = Field(default=2, ge=0)
    requires_consecutive: bool = Field(default=False, description="是否需要连排")
    requires_lab: bool = Field(default=False, description="是否需要实验室")
    priority: int = Field(default=0, ge=0, le=10, description="优先级")
    department: Optional[str] = Field(None, max_length=100)
    program_id: Optional[int] = Field(None, ge=1)
    direction_id: Optional[int] = Field(None, ge=1)
    offering_unit_id: Optional[int] = Field(None, ge=1)
    leader_teacher_id: Optional[int] = Field(None, ge=1)
    remarks: Optional[str] = None
    is_active: bool = True

    @field_validator('weekdays', mode='before')
    @classmethod
    def validate_weekdays(cls, value):
        return _clean_weekdays(value)


class CourseCreate(CourseBase):
    """创建课程"""
    semester: int = Field(..., ge=1, le=12, description="上课学期（培养方案学期）")


class CourseUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    """更新课程"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    course_code: Optional[str] = Field(None, min_length=1, max_length=50)
    course_type: Optional[str] = None
    course_nature: Optional[str] = None
    semester: Optional[int] = Field(None, ge=1, le=12)
    cohort: Optional[str] = Field(None, max_length=20)
    teaching_weeks: Optional[int] = Field(None, ge=1, le=20)
    tail_hours: Optional[int] = Field(None, ge=0)
    weekdays: Optional[list[int]] = None
    total_hours: Optional[int] = Field(None, ge=0)
    credits: Optional[float] = Field(None, ge=0)
    requires_consecutive: Optional[bool] = None
    requires_lab: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0, le=10)
    department: Optional[str] = None
    program_id: Optional[int] = Field(None, ge=1)
    direction_id: Optional[int] = Field(None, ge=1)
    offering_unit_id: Optional[int] = Field(None, ge=1)
    leader_teacher_id: Optional[int] = Field(None, ge=1)
    remarks: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator('weekdays')
    @classmethod
    def validate_weekdays(cls, value):
        return _clean_weekdays(value)


class CourseResponse(CourseBase):
    """课程响应"""
    id: int
    offering_unit_name: Optional[str] = None
    program_name: Optional[str] = None
    direction_name: Optional[str] = None
    leader_teacher_name: Optional[str] = None
    leader_teacher_code: Optional[str] = None
    curriculum_sources: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
