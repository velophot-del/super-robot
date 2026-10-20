from sqlalchemy import text

IMMUTABLE=['planning_events','published_plans','preference_submissions','teacher_match_runs','curriculum_documents']


def install_immutable_triggers(engine):
    if engine.dialect.name!='sqlite':return
    with engine.begin() as conn:
        for table in IMMUTABLE:
            for operation in ['UPDATE','DELETE']:
                conn.execute(text(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable record'); END"))
