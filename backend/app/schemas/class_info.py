"""班级相关Pydantic模式"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ClassInfoBase(BaseModel):
    """班级基础字段"""
    name: str = Field(..., min_length=1, max_length=100, description="班级名称")
    grade: str = Field(..., pattern=r'^\d{4}(届|级)?$', description="入学年级，如2026级")
    student_count: int = Field(default=0, ge=0, description="学生人数")
    department: Optional[str] = Field(None, max_length=100)
    program_id: Optional[int] = Field(None, ge=1)
    homeroom_teacher: Optional[str] = Field(None, max_length=50)
    remarks: Optional[str] = None
    is_active: bool = True


class ClassInfoCreate(ClassInfoBase):
    """创建班级"""
    pass


class ClassInfoUpdate(BaseModel):
    """更新班级（所有字段可选）"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    grade: Optional[str] = Field(None, pattern=r'^\d{4}(届|级)?$')
    student_count: Optional[int] = Field(None, ge=0)
    department: Optional[str] = Field(None, max_length=100)
    program_id: Optional[int] = Field(None, ge=1)
    homeroom_teacher: Optional[str] = Field(None, max_length=50)
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class ClassInfoResponse(ClassInfoBase):
    """班级响应"""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
