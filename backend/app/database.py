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
    _migrate_academic_catalog_detail(engine)
    _seed_default_offering_units(engine)
    _seed_academic_catalog_detail(engine)
    _backfill_master_data_links(engine)
    from app.services.immutable_records import install_immutable_triggers
    install_immutable_triggers(engine)


def _seed_default_offering_units(engine):
    """Install the five stable studio records without undoing admin renames."""
    from app.models.planning import OfferingUnit
    from app.models.teacher import Teacher
    from sqlalchemy.orm import Session

    defaults = [
        ('DEPT-01', '视觉传达设计', '视觉策略与叙事设计教研室'),
        ('DEPT-02', '包装设计', '包装系统与可持续设计教研室'),
        ('DEPT-03', '数字艺术', '数字艺术与媒介创新教研室'),
        ('DEPT-04', '时尚传播', '视觉系统与时尚传播教研室'),
        ('DEPT-05', '智能交互设计', '智能交互与体验设计教研室'),
    ]
    with Session(engine) as db:
        for code, legacy_name, name in defaults:
            row = db.query(OfferingUnit).filter_by(code=code).first()
            if row:
                if row.name == legacy_name:
                    db.query(Teacher).filter(Teacher.department == legacy_name).update(
                        {Teacher.department: name}, synchronize_session=False)
                    row.name = name
                continue
            if db.query(OfferingUnit.id).filter_by(name=name).first():
                continue
            db.add(OfferingUnit(code=code, name=name))
        db.commit()


def _migrate_academic_catalog_detail(engine):
    """Add catalog detail fields to existing program tables."""
    if 'sqlite' not in str(engine.url):
        return
    from sqlalchemy import inspect, text
    columns = {column['name'] for column in inspect(engine).get_columns('academic_programs')}
    with engine.begin() as connection:
        for name, definition in (
            ('education_level', "VARCHAR(20) NOT NULL DEFAULT '本科'"),
            ('degree_category', 'VARCHAR(30)'),
            ('construction_level', 'VARCHAR(300)'),
            ('source_notes', 'VARCHAR(1000)'),
        ):
            if name not in columns:
                connection.execute(text(f'ALTER TABLE academic_programs ADD COLUMN {name} {definition}'))


def _seed_academic_catalog_detail(engine):
    """Seed the workbook's program and direction catalog once, preserving admin edits."""
    from sqlalchemy.orm import Session
    from app.models.planning import AcademicCatalogSeed, AcademicDirection, AcademicProgram, OfferingUnit

    source = [
        {'code':'130502','name':'视觉传达设计','degree':'艺术学','level':'国家级一流本科专业建设点（首批）','notes':'本科；学制四年。'},
        {'code':'130508','name':'数字媒体艺术','degree':'艺术学','level':'山东省一流本科专业建设点','notes':'汇总表名称写作“数字媒体艺术（交互设计）”；明细表写作“数字媒体艺术”。明细方向数与汇总表方向数不一致，待核对。'},
        {'code':'081702','name':'包装工程','degree':'工学','level':'山东省一流本科专业建设点','notes':'本科；学制四年。理工类招生。'},
        {'code':'130512T','name':'包装设计','degree':'艺术学','level':'2024年起招生（2025软科专业排名第2）','notes':'特设专业；2016年新增，我院2024年起招生。排名信息以原表口径为准。'},
        {'code':'080218T','name':'智能交互设计','degree':'工学','level':'2022年增设（特设专业）','notes':'由数字媒体艺术（交互设计）延续发展而来；授工学学位。'},
        {'code':'080808T','name':'智能工程与创意设计','degree':'工学','level':'新设专业（已获教育部批复）','notes':'获批年度在原表中存在2024/2025口径差异；教研室归属建议学院核实。'},
    ]
    directions = [
        ('130502','品牌与视觉策略','专业方向','DEPT-01','方向侧重品牌策略、视觉识别与整合传播',1),
        ('130502','插画与叙事设计','专业方向','DEPT-01','对应核心课程：出版物设计、插画与绘本设计',2),
        ('130502','时尚传播','专业方向','DEPT-04','此处为130502下设方向，与独立专业包装设计（130512T）名称相同但代码不同',3),
        ('130508','整专业招生（交互设计口径）','整专业招生','DEPT-03','明细表将其列为整专业招生；汇总表方向数为0，原表统计说明称未细分专业计1，口径待核实',4),
        ('081702','整专业招生（未细分方向）','整专业招生','DEPT-02','理工类招生，授工学学位',5),
        ('130512T','整专业招生（未细分方向）','整专业招生','DEPT-02','“T”为特设专业',6),
        ('080218T','整专业招生（未细分方向）','整专业招生','DEPT-05','“T”为特设专业',7),
        ('080808T','整专业招生（未细分方向）','整专业招生','DEPT-05','教研室归属待学院确认',8),
    ]
    with Session(engine) as db:
        seed_key='vcd-professional-directory-v1'
        if db.get(AcademicCatalogSeed,seed_key):
            return
        programs = {}
        for item in source:
            row = db.query(AcademicProgram).filter_by(code=item['code']).first()
            if not row:
                row = db.query(AcademicProgram).filter_by(name=item['name']).first()
            if not row and item['code'] == '130508':
                row = db.query(AcademicProgram).filter_by(name='数字媒体艺术（交互设计）').first()
            if not row:
                row = AcademicProgram(code=item['code'], name=item['name'], duration_semesters=8)
                db.add(row)
                db.flush()
            else:
                if row.code.startswith('LEGACY-') and not db.query(AcademicProgram.id).filter_by(code=item['code']).first():
                    row.code = item['code']
                if row.name == '数字媒体艺术（交互设计）' and not db.query(AcademicProgram.id).filter_by(name=item['name']).first():
                    row.name = item['name']
            for attr, value in (
                ('education_level','本科'), ('degree_category',item['degree']),
                ('construction_level',item['level']), ('source_notes',item['notes']),
            ):
                if getattr(row, attr) in (None, '') or (attr == 'education_level' and getattr(row, attr) == '本科'):
                    setattr(row, attr, value)
            programs[item['code']] = row
        db.flush()
        existing_program_ids = {row[0] for row in db.query(AcademicDirection.program_id).distinct()}
        for code, name, entry_type, unit_code, notes, order in directions:
            program = programs[code]
            if program.id in existing_program_ids:
                continue
            unit = db.query(OfferingUnit).filter_by(code=unit_code).first()
            db.add(AcademicDirection(program_id=program.id, name=name, entry_type=entry_type,
                                     offering_unit_id=unit.id if unit else None,
                                     notes=notes, source_order=order))
        db.flush()
        db.add(AcademicCatalogSeed(seed_key=seed_key))
        db.commit()


def _backfill_master_data_links(engine):
    """Backfill exact legacy labels after the administrator catalog is seeded."""
    if 'sqlite' not in str(engine.url):
        return
    from sqlalchemy import text
    with engine.begin() as connection:
        connection.execute(text('''UPDATE classes SET program_id=(SELECT id FROM academic_programs WHERE name=classes.department)
            WHERE program_id IS NULL AND department IS NOT NULL
            AND (SELECT COUNT(*) FROM academic_programs WHERE name=classes.department)=1'''))
        connection.execute(text('''UPDATE courses SET program_id=(SELECT id FROM academic_programs WHERE name=courses.department)
            WHERE program_id IS NULL AND department IS NOT NULL
            AND (SELECT COUNT(*) FROM academic_programs WHERE name=courses.department)=1'''))
        connection.execute(text('''UPDATE teachers SET offering_unit_id=(SELECT id FROM offering_units WHERE name=teachers.department)
            WHERE offering_unit_id IS NULL AND department IS NOT NULL
            AND (SELECT COUNT(*) FROM offering_units WHERE name=teachers.department)=1'''))


def _migrate_teacher_columns(engine):
    from sqlalchemy import inspect, text
    columns = {column['name'] for column in inspect(engine).get_columns('teachers')}
    with engine.begin() as connection:
        for name, definition in [('position', 'VARCHAR(50)'), ('review_major', 'VARCHAR(100)')]:
            if name not in columns:
                connection.execute(text(f'ALTER TABLE teachers ADD COLUMN {name} {definition}'))


def _migrate_course_columns(engine):
    """SQLite 兼容迁移：新增每周上课日，删除旧次数/课时列并回填授课周数。"""
    from sqlalchemy import text

    # 仅 SQLite 需要手动迁移
    if "sqlite" not in str(engine.url):
        return

    with engine.begin() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(courses)")).fetchall()}

        # 1. 新增每周固定上课日
        if "weekdays" not in existing:
            conn.execute(text("ALTER TABLE courses ADD COLUMN weekdays JSON NOT NULL DEFAULT '[]'"))
            existing.add("weekdays")
        conn.execute(text("UPDATE courses SET weekdays='[]' WHERE weekdays IS NULL OR weekdays='null'"))

        # 2. 授课周数：旧数据仅有次数时，先按次数÷每周次数回填
        if "teaching_weeks" not in existing:
            conn.execute(text("ALTER TABLE courses ADD COLUMN teaching_weeks INTEGER"))
            existing.add("teaching_weeks")
        if {"semester_sessions", "weekly_sessions"} <= existing:
            conn.execute(text("""
                UPDATE courses SET teaching_weeks =
                    MAX(1, CAST((semester_sessions + weekly_sessions - 1) / weekly_sessions AS INTEGER))
                WHERE teaching_weeks IS NULL AND semester_sessions IS NOT NULL AND weekly_sessions > 0
            """))

        # 3. 彻底删除不再使用的次数/课时列
        for column in ("semester_sessions", "weekly_sessions", "hours_per_session", "weekly_hours"):
            if column in existing:
                try:
                    conn.execute(text(f"ALTER TABLE courses DROP COLUMN {column}"))
                    existing.discard(column)
                except Exception:
                    pass  # 旧版 SQLite 不支持 DROP COLUMN 时保留列，代码不再引用

        # Existing courses retain a null leader until an administrator explicitly assigns one.
        if "leader_teacher_id" not in existing:
            conn.execute(text("ALTER TABLE courses ADD COLUMN leader_teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL"))
        if "course_nature" not in existing:
            conn.execute(text("ALTER TABLE courses ADD COLUMN course_nature VARCHAR(20) NOT NULL DEFAULT '必修课'"))
        if "semester" not in existing:
            conn.execute(text("ALTER TABLE courses ADD COLUMN semester INTEGER"))
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
                'program_id': 'INTEGER REFERENCES academic_programs(id)',
                'direction_id': 'INTEGER REFERENCES academic_directions(id)',
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
            'teachers': {'offering_unit_id': 'INTEGER REFERENCES offering_units(id)'},
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

        # Exact-name backfill only. Ambiguous or unmatched legacy labels remain for data-check review.
        conn.execute(text('''UPDATE courses SET program_id=(SELECT id FROM academic_programs WHERE name=courses.department)
            WHERE program_id IS NULL AND department IS NOT NULL
            AND (SELECT COUNT(*) FROM academic_programs WHERE name=courses.department)=1'''))
        conn.execute(text('''UPDATE teachers SET offering_unit_id=(SELECT id FROM offering_units WHERE name=teachers.department)
            WHERE offering_unit_id IS NULL AND department IS NOT NULL
            AND (SELECT COUNT(*) FROM offering_units WHERE name=teachers.department)=1'''))
