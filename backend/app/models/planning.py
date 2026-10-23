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
    program_id = Column(Integer, ForeignKey('academic_programs.id'), nullable=True)
    offering_unit_id = Column(Integer, ForeignKey('offering_units.id'), nullable=True)
    duration_semesters = Column(Integer, nullable=False, default=8)
    __table_args__ = (UniqueConstraint('major', 'cohort', 'revision'),)


class ActiveCurriculum(Base):
    __tablename__ = 'active_curricula'
    id = Column(Integer, primary_key=True)
    major = Column(String, nullable=False)
    cohort = Column(String, nullable=False)
    document_id = Column(Integer, ForeignKey('curriculum_documents.id'), nullable=False)
    program_id = Column(Integer, ForeignKey('academic_programs.id'), nullable=True)
    __table_args__ = (UniqueConstraint('major', 'cohort'),)


class CurriculumCourse(Base):
    __tablename__ = 'curriculum_courses'
    id = Column(Integer,primary_key=True)
    document_id = Column(Integer,ForeignKey('curriculum_documents.id'),nullable=False)
    row_code = Column(String,nullable=False)
    course_id = Column(Integer,ForeignKey('courses.id'),nullable=False)
    metadata_json = Column(JSON,nullable=False)
    __table_args__ = (UniqueConstraint('document_id','row_code'),)


class AcademicProgram(Base, TimestampMixin):
    __tablename__ = 'academic_programs'
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), unique=True, nullable=False)
    duration_semesters = Column(Integer, nullable=False, default=8)
    is_active = Column(Boolean, nullable=False, default=True)


class OfferingUnit(Base, TimestampMixin):
    __tablename__ = 'offering_units'
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class ImportPreviewBatch(Base, TimestampMixin):
    __tablename__ = 'import_preview_batches'
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(30), nullable=False)
    filename = Column(String(200), nullable=False)
    file_sha256 = Column(String(64), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    status = Column(String(20), nullable=False, default='pending')
    payload = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class TeacherScheduleConfirmation(Base, TimestampMixin):
    __tablename__ = 'teacher_schedule_confirmations'
    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey('published_plans.id'), nullable=False)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    task_id = Column(Integer, nullable=False)
    teacher_id = Column(Integer, ForeignKey('teachers.id'), nullable=False)
    status = Column(String(30), nullable=False)
    note = Column(String(500), nullable=True)


class ScheduleChangeRequest(Base, TimestampMixin):
    __tablename__ = 'schedule_change_requests'
    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey('published_plans.id'), nullable=False)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    task_id = Column(Integer, nullable=False)
    teacher_id = Column(Integer, ForeignKey('teachers.id'), nullable=False)
    reason = Column(String(1000), nullable=False)
    desired_change = Column(String(1000), nullable=True)


class ScheduleChangeDecision(Base, TimestampMixin):
    __tablename__ = 'schedule_change_decisions'
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey('schedule_change_requests.id'), nullable=False)
    admin_actor = Column(String(120), nullable=False)
    decision = Column(String(20), nullable=False)
    reason = Column(String(1000), nullable=True)
    revision_plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=True)


class TeacherNotification(Base, TimestampMixin):
    __tablename__ = 'teacher_notifications'
    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey('teachers.id'), nullable=False)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    kind = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=False)


class AutoSchedulePreview(Base, TimestampMixin):
    __tablename__ = 'auto_schedule_previews'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('academic_plans.id'), nullable=False)
    plan_revision = Column(Integer, nullable=False)
    algorithm = Column(String(30), nullable=False)
    payload = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


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
