# Project rules

- Use Chinese for user communication; preserve English code and file names.
- Stack: FastAPI + SQLAlchemy backend, React + TypeScript + Ant Design frontend.
- Keep changes focused. Do not install new dependencies or submit/push code without user approval.
- Preserve existing data and user edits. This directory currently has no Git metadata.

## Local development

- Backend virtual environment: `backend/.venv` (Python 3.12).
- Frontend dependencies: `frontend/node_modules`.
- Bind local services to `127.0.0.1`; backend port 8000, frontend port 5173.
- Set `DEBUG=false` explicitly when running Python commands: the host environment may set an incompatible `DEBUG` string.
- Debug demo startup and database isolation are documented in `DEBUG.md`.
- Demo mode defaults off. Enable only with a dedicated demo database and matching `DATABASE_URL` / `DEBUG_DEMO_DATABASE_URL`.
- Access uses AccountGrant capabilities and scopes plus TeacherBinding, not role labels. Normal accounts without explicit grants are denied; `backend/app/access_cli.py` previews explicit grants and only writes with `--apply`. Do not grant accounts automatically outside an explicitly authorized roster import. Administrator CSV teacher imports provision work-number usernames, initial password 123456, TeacherBinding and teaching@self only; repeated imports must never reset passwords or claim conflicting existing accounts.
- New workflow is `/api/planning` and `/planning`: teacher preferences precede matching, manual review and publication. Legacy GA pages are not this workflow. See `PLANNING_WORKFLOW.md` for implemented scope and remaining requirements.
- Keep submitted preferences, match runs, source documents, audit events and publication snapshots immutable. SQLite triggers enforce this after `init_db`.
- Task setup and opening preferences allow empty periods and no room; validate stage spans, positive required hours and the two-course weekly limit. Require complete periods, exact teaching hours and a valid room before publication. Preserve existing mode and periods when task edits omit these hidden fields. Same student group: at most two courses weekly and one per day; reserved periods do not count as teaching hours.

## Checks

- Administrator-managed Teacher.position (主任 or 副主任) and review_major contribute scoped lead@dept access for the bound teacher account; demotion removes only appointment-derived access. Never derive review scope from self-declared profiles or create/claim accounts when editing appointments.

From `backend`:

```bash
DEBUG=false PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

From `frontend`:

```bash
npm test
npm run build
npm run lint
```

`npm test` uses native Node tests and TypeScript stripping, verified with local Node 25. No extra test dependency is required. Report existing build/lint failures explicitly rather than weakening checks. Backend tests use in-memory SQLite; do not use the live demo database for test fixtures.

- College Word export template: `backend/app/templates/college_stage_timetable.docx`. Preserve it; generate from published snapshots using `word_timetable.py`. Do not claim exact visual fidelity without rendered page inspection.
- Curriculum rows without official codes use marked SYS internal IDs. Preserve original fields; unknown semester, zero teaching hours, placeholder or duplicate-name/semester rows are not automatically scheduled.

- Teacher declarations live under TeacherProfile.payload.self_profile; preserve administrator records on self updates and preserve declarations on admin updates. Gate draft/save and submission server-side on complete self-profile.
- Teacher selection filters academic year/semester/major, but retains separate drafts/submissions per administrator cycle; do not silently introduce annual unified submission. Administrative verified records and self declarations must have distinct provenance in matching.

- For a 20-week cycle, weeks 1–19 are teaching weeks and week 20 is reserved for exams. Validate the final week exclusion in placement, task validation, teacher grids and Word exports.
- Active curriculum activation and course-pool sync populate canonical courses idempotently; preserve original course fields and keep source metadata in curriculum_courses. Administrator stage planning uses class rows and 20 week columns; unplacing retains source tasks.

- Public registration is disabled. Imported real accounts must change the initial password and complete their self-profile before business access; enforce this in require_user and the frontend route guard. AccountSetup is a separate table so existing accounts and passwords are preserved. Password changes increment the token version and invalidate prior tokens. Demo identities do not have real account passwords.

- Administrator task settings expose only teacher_count and max_students through the revision-checked limits endpoint. Course information is read-only from imported metadata; use the 20-week grid for placement. Keep max_students separate from actual class size and check it on save, placement, opening and publication. Teacher preselection ignores tail-only cell boundaries; retain original periods and published snapshots.

- Personal workload estimates are optional planning aids stored separately by teacher/plan/task; never overwrite preference submissions or use class size/student caps as personal guidance counts. Personal Excel export always filters by the server-bound teacher even for dual admin accounts, and uses the selected plan latest immutable published snapshot.
