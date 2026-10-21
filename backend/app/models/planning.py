"""新版教师意愿和阶段计划；旧资源表与旧课表保持不变。"""
from sqlalchemy import Column, Integer, String, JSON, Date, DateTime, Boolean, ForeignKey, UniqueConstraint, LargeBinary
from app.database import Base
from app.models.base import TimestampMixin


class AccountGrant(Base):
    __tablename__ = 'account_grants'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    capability = Column(String, nullable=False)
    scope = Column(String, nullable=False, default='all')
    scope_id = Column(String, nullable=False, default='')
    __table_args__ = (UniqueConstraint('user_id', 'capability', 'scope', 'scope_id'),)


class TeacherBinding(Base):
    __tablename__ = 'teacher_bindings'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    teacher_id = Column(Integer, ForeignKey('teachers.id'), unique=True, nullable=False)


class TeacherProfile(Base):
    __tablename__ = 'teacher_profiles'
    teacher_id = Column(Integer, ForeignKey('teachers.id'), primary_key=True)
    payload = Column(JSON, nullable=False)
    revision = Column(Integer, default=1, nullable=False)


class AcademicPlan(Base, TimestampMixin):
    __tablename__ = 'academic_plans'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    weeks = Column(Integer, nullable=False, default=20)
    deadline = Column(DateTime, nullable=False)
    state = Column(String, default='draft', nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    rule_confirmed = Column(Boolean, default=False, nullable=False)
    settings = Column(JSON, nullable=False, default=dict)


class TeachingTask(Base):
    __tablename__ = 'teaching_tasks'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    payload = Column(JSON, nullable=False)


class PeriodSlot(Base):
    __tablename__ = 'period_slots'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('teaching_tasks.id'), nullable=False)
    day = Column(Integer, nullable=False)
    start = Column(Integer, nullable=False)
    count = Column(Integer, nullable=False)
    phase = Column(String, nullable=False, default='normal')


class PreferenceDraft(Base):
    __tablename__ = 'preference_drafts'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    teacher_id = Column(Integer, ForeignKey('teachers.id'), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    plan_revision = Column(Integer, nullable=False)
    task_ids = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('plan_id', 'teacher_id'),)


class PreferenceSubmission(Base, TimestampMixin):
    __tablename__ = 'preference_submissions'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    teacher_id = Column(Integer, ForeignKey('teachers.id'), nullable=False)
    plan_revision = Column(Integer, nullable=False)
    draft_revision = Column(Integer, nullable=False)
    task_ids = Column(JSON, nullable=False)


class MatchRun(Base, TimestampMixin):
    __tablename__ = 'teacher_match_runs'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    payload = Column(JSON, nullable=False)


class TeachingAssignment(Base):
    __tablename__ = 'teaching_assignments'
    task_id = Column(Integer, ForeignKey('teaching_tasks.id'), primary_key=True)
    teacher_ids = Column(JSON, nullable=False)
    match_id = Column(Integer, ForeignKey('teacher_match_runs.id'), nullable=False)
    locked = Column(Boolean, nullable=False, default=True)


class PlanningEvent(Base, TimestampMixin):
    __tablename__ = 'planning_events'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'))
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)


class PublishedPlan(Base, TimestampMixin):
    __tablename__ = 'published_plans'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    payload = Column(JSON, nullable=False)


class CurriculumDocument(Base, TimestampMixin):
    __tablename__ = 'curriculum_documents'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    major = Column(String, nullable=False)
    cohort = Column(String, nullable=False)
    revision = Column(Integer, nullable=False)
    original = Column(LargeBinary, nullable=False)
    sha256 = Column(String, nullable=False)
    rows = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('major', 'cohort', 'revision'),)


class ActiveCurriculum(Base):
    __tablename__ = 'active_curricula'
    id = Column(Integer, primary_key=True)
    major = Column(String, nullable=False)
    cohort = Column(String, nullable=False)
    document_id = Column(Integer, ForeignKey('curriculum_documents.id'), nullable=False)
    __table_args__ = (UniqueConstraint('major', 'cohort'),)


class CurriculumCourse(Base):
    __tablename__ = 'curriculum_courses'
    id = Column(Integer,primary_key=True)
    document_id = Column(Integer,ForeignKey('curriculum_documents.id'),nullable=False)
    row_code = Column(String,nullable=False)
    course_id = Column(Integer,ForeignKey('courses.id'),nullable=False)
    metadata_json = Column(JSON,nullable=False)
    __table_args__ = (UniqueConstraint('document_id','row_code'),)


class TeacherWorkloadEstimate(Base):
    """本人授课周数/指导人数参数，不改写选课记录或发布快照。"""
    __tablename__ = 'teacher_workload_estimates'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    teacher_id = Column(Integer, ForeignKey('teachers.id'), nullable=False)
    task_id = Column(Integer, ForeignKey('teaching_tasks.id'), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    payload = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('plan_id','teacher_id','task_id'),)
