"""数据库连接与会话管理"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# 创建引擎
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=settings.DEBUG,
)

# 启用SQLite外键约束
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in settings.DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()


def get_db():
    """获取数据库会话（依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表结构（含自动迁移）"""
    Base.metadata.create_all(bind=engine)
    _migrate_course_columns(engine)
    _migrate_class_columns(engine)
    _migrate_teacher_columns(engine)
    _migrate_academic_scope_columns(engine)
    from app.services.immutable_records import install_immutable_triggers
    install_immutable_triggers(engine)


def _migrate_teacher_columns(engine):
    from sqlalchemy import inspect, text
    columns = {column['name'] for column in inspect(engine).get_columns('teachers')}
    with engine.begin() as connection:
        for name, definition in [('position', 'VARCHAR(50)'), ('review_major', 'VARCHAR(100)')]:
            if name not in columns:
                connection.execute(text(f'ALTER TABLE teachers ADD COLUMN {name} {definition}'))


def _migrate_course_columns(engine):
    """SQLite 兼容迁移：重命名 weekly_hours → semester_sessions + 新增列"""
    import sqlite3
    from sqlalchemy import text, inspect

    # 仅 SQLite 需要手动迁移
    if "sqlite" not in str(engine.url):
        return

    with engine.connect() as conn:
        # 获取现有列名
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(courses)")).fetchall()}

        # 1. 如果旧列 weekly_hours 存在且新列 semester_sessions 不存在，执行重命名
        if "weekly_hours" in existing and "semester_sessions" not in existing:
            try:
                conn.execute(text("ALTER TABLE courses RENAME COLUMN weekly_hours TO semester_sessions"))
                conn.commit()
                existing.discard("weekly_hours")
                existing.add("semester_sessions")
            except Exception:
                pass  # 忽略迁移错误（列可能已被其他方式处理）

        # 2. 新增 weekly_sessions 列
        if "weekly_sessions" not in existing:
            try:
                conn.execute(text("ALTER TABLE courses ADD COLUMN weekly_sessions INTEGER NOT NULL DEFAULT 1"))
                conn.commit()
            except Exception:
                pass

        # 3. 新增 hours_per_session 列
        if "hours_per_session" not in existing:
            try:
                conn.execute(text("ALTER TABLE courses ADD COLUMN hours_per_session INTEGER NOT NULL DEFAULT 2"))
                conn.commit()
            except Exception:
                pass

        # Existing courses retain a null leader until an administrator explicitly assigns one.
        if "leader_teacher_id" not in existing:
            conn.execute(text("ALTER TABLE courses ADD COLUMN leader_teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL"))
            conn.commit()
        if "course_nature" not in existing:
            conn.execute(text("ALTER TABLE courses ADD COLUMN course_nature VARCHAR(20) NOT NULL DEFAULT '必修课'"))
            conn.commit()
        if "semester" not in existing:
            conn.execute(text("ALTER TABLE courses ADD COLUMN semester INTEGER"))
            conn.commit()
        if "course_type" in existing:
            conn.execute(text("""UPDATE courses SET
                course_nature=CASE
                    WHEN course_type LIKE '%任选%' OR course_nature LIKE '%任选%' THEN '任选课'
                    WHEN course_type LIKE '%限选%' OR course_type LIKE '%选修%' OR course_nature LIKE '%限选%' OR course_nature='选修' THEN '限选课'
                    WHEN course_nature IN ('必修','必修课') THEN '必修课'
                    ELSE '必修课' END,
                course_type=CASE
                    WHEN course_type IN ('学科通识课','德育通识课','综合实践课','跨专业交叉课','国际课程','专业课') THEN course_type
                    WHEN course_type LIKE '%国际%' THEN '国际课程'
                    WHEN course_type LIKE '%交叉%' OR course_type LIKE '%跨专业%' THEN '跨专业交叉课'
                    WHEN course_type LIKE '%德育%' OR course_type LIKE '%思政%' THEN '德育通识课'
                    WHEN course_type LIKE '%实践%' THEN '综合实践课'
                    WHEN course_type LIKE '%公共%' OR course_type LIKE '%通识%' THEN '学科通识课'
                    ELSE '专业课' END"""))
            conn.commit()


def _migrate_class_columns(engine):
    """SQLite 兼容迁移：旧班级默认视为有效班级。"""
    if "sqlite" not in str(engine.url):
        return
    from sqlalchemy import text
    with engine.begin() as conn:
        columns={row[1] for row in conn.execute(text("PRAGMA table_info(classes)"))}
        if "is_active" not in columns:
            conn.execute(text("ALTER TABLE classes ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))


def _migrate_academic_scope_columns(engine):
    """为方案专业、开课单位增加稳定标识；旧记录仅按精确名称自动回填。"""
    if "sqlite" not in str(engine.url):
        return
    import hashlib
    from sqlalchemy import text
    with engine.begin() as conn:
        additions = {
            'classes': {'program_id': 'INTEGER REFERENCES academic_programs(id)'},
            'courses': {
                'offering_unit_id': 'INTEGER REFERENCES offering_units(id)',
                'cohort': 'VARCHAR(20)',
                'teaching_weeks': 'INTEGER',
                'tail_hours': 'INTEGER',
                'is_active': 'BOOLEAN NOT NULL DEFAULT 1',
            },
            'curriculum_documents': {
                'program_id': 'INTEGER REFERENCES academic_programs(id)',
                'offering_unit_id': 'INTEGER REFERENCES offering_units(id)',
                'duration_semesters': 'INTEGER NOT NULL DEFAULT 8',
            },
            'active_curricula': {'program_id': 'INTEGER REFERENCES academic_programs(id)'},
        }
        for table, columns in additions.items():
            existing = {row[1] for row in conn.execute(text(f'PRAGMA table_info({table})'))}
            for column, definition in columns.items():
                if column not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {definition}'))

        archived = conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='curriculum_documents_no_update'")).first()
        majors = [row[0] for row in conn.execute(
            text('SELECT DISTINCT major FROM curriculum_documents WHERE trim(major) != ""')).fetchall()]
        for name in majors:
            record = conn.execute(text('SELECT id FROM academic_programs WHERE name=:name'), {'name': name}).first()
            if record:
                program_id = record[0]
            else:
                code = 'LEGACY-' + hashlib.sha1(name.encode('utf-8')).hexdigest()[:12].upper()
                conn.execute(text('INSERT OR IGNORE INTO academic_programs (code,name,duration_semesters,is_active) VALUES (:code,:name,8,1)'),
                             {'code': code, 'name': name})
                program_id = conn.execute(text('SELECT id FROM academic_programs WHERE name=:name'), {'name': name}).scalar()
            if not archived:
                conn.execute(text('UPDATE curriculum_documents SET program_id=:pid WHERE major=:name AND program_id IS NULL'),
                             {'pid': program_id, 'name': name})
            conn.execute(text('UPDATE active_curricula SET program_id=:pid WHERE major=:name AND program_id IS NULL'),
                         {'pid': program_id, 'name': name})
            # A class with a multi-major or non-exact label remains unbound for administrator review.
            conn.execute(text('UPDATE classes SET program_id=:pid WHERE department=:name AND program_id IS NULL'),
                         {'pid': program_id, 'name': name})
