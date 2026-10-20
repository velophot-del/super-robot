from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator, ConfigDict


class PlanInput(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    start_date: date
    weeks: int = Field(20, ge=18, le=20)
    deadline: datetime
    rule_confirmed: bool = False
    major: str = ''
    cohort: str = ''
    semester: int = Field(2, ge=1, le=12)
    groups: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def monday(self):
        if self.start_date.weekday() != 0:
            raise ValueError('学期第1周须从周一开始')
        return self


class SlotInput(BaseModel):
    day: int = Field(ge=1, le=7)
    start: int = Field(ge=1, le=8)
    count: int = Field(ge=1, le=8)
    phase: str = Field('normal', pattern='^(normal|tail)$')

    @model_validator(mode='after')
    def end(self):
        if self.start + self.count > 9:
            raise ValueError('上课节次不能超过第8节')
        return self


class TaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    group: str = Field(min_length=1, max_length=100)
    class_name: str = ''
    student_ids: list[str] = Field(default_factory=list, max_length=1000)
    department: str = Field(min_length=1)
    credits: float = Field(ge=0, le=30)
    required_hours: int = Field(ge=1, le=400)
    start_week: int = Field(ge=1, le=20)
    end_week: int = Field(ge=1, le=20)
    tail_weeks: int = Field(0, ge=0, le=20)
    slots: list[SlotInput] = Field(min_length=1, max_length=14)
    direction: str = ''
    tags: list[str] = Field(default_factory=list)
    profile_verified: bool = False
    teacher_count: int = Field(1, ge=1, le=5)
    mode: str = Field('single', pattern='^(single|segment|group|collaborative)$')
    student_count: int = Field(30, ge=1)
    room_id: int | None = None
    room_type: str = ''
    source: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def weeks(self):
        if self.start_week > self.end_week or self.tail_weeks >= self.end_week-self.start_week+1:
            raise ValueError('起止周或尾段周数无效')
        if self.tail_weeks and not any(s.phase == 'tail' for s in self.slots):
            raise ValueError('尾段需要独立设置周内分布')
        if len({(s.phase, s.day) for s in self.slots}) != len(self.slots):
            raise ValueError('同阶段同一天只设置一个连续节次区间')
        return self


class ProfileInput(BaseModel):
    direction: str = ''
    tags: list[str] = Field(default_factory=list)
    verified: bool = False
    team_codes: list[str] = Field(default_factory=list)
    taught_codes: list[str] = Field(default_factory=list)
    weekly_limit: int = Field(20, ge=0, le=40)
    course_limit: int = Field(3, ge=1, le=30)
    external_hours: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode='after')
    def external(self):
        if any(not w.isdigit() or not 1 <= int(w) <= 20 or h < 0 or h > 40 for w,h in self.external_hours.items()):
            raise ValueError('外部课时按1—20周填写0—40节')
        return self


class DraftInput(BaseModel):
    revision: int = Field(ge=0)
    plan_revision: int = Field(ge=1)
    task_ids: list[int] = Field(max_length=5)


class SubmitInput(BaseModel):
    revision: int = Field(ge=1)


class AssignmentInput(BaseModel):
    task_id: int
    teacher_ids: list[int] = Field(min_length=1, max_length=5)
    match_id: int
    reason: str = Field(min_length=1, max_length=1000)


class SelfProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    direction: str = Field(min_length=1,max_length=100)
    tags: list[str] = Field(min_length=1,max_length=30)
    skilled_courses: list[str] = Field(min_length=1,max_length=50)
    introduction: str = Field('',max_length=2000)
    contact_email: str = Field('',max_length=200)
    contact_phone: str = Field('',max_length=50)

    @model_validator(mode='after')
    def clean(self):
        self.direction=self.direction.strip()
        self.tags=list(dict.fromkeys(t.strip() for t in self.tags if t.strip()))
        self.skilled_courses=list(dict.fromkeys(t.strip() for t in self.skilled_courses if t.strip()))
        if not self.direction or not self.tags or not self.skilled_courses:
            raise ValueError('专业方向、专业领域和擅长课程均须填写')
        if any(len(t)>200 for t in self.tags+self.skilled_courses):raise ValueError('单条领域或课程名称不能超过200字')
        return self
