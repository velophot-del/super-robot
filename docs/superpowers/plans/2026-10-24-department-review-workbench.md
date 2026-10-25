# 教研室主任审核工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 主任查看本室负责专业班级的全部课程、提出逐门排课调剂并提交管理员确认，同时获得精简的 AI 审查摘要。

**Architecture:** 在现有 PlanningEvent 不可变审计流中追加独立的课程调剂草案/送审/审核事件，不在主任保存时修改正式 TeachingTask、PeriodSlot 或 TeachingAssignment。新增受范围约束的课程板与草案 API；管理员确认时在一个事务中重新校验并应用排课、教师分配、教室和周内节次。前端改造主任工作台与管理员待办，复用现有甘特图、任务资源选项及排课校验。

**Tech Stack:** FastAPI、SQLAlchemy、SQLite、React、TypeScript、Ant Design、原生 Node 测试与 Python unittest。

**Spec:** `docs/superpowers/specs/2026-10-24-department-review-workbench-design.md`

## Global Constraints

- 仅使用管理员维护的教研室/专业/班级映射授权数据；不从教师申报扩大范围。
- 主任提出教师调剂建议，管理员最终确认；主任不能确认或发布。
- AI 审查为只读建议，不批准、不分配、不写入课表。
- 正式任务只在管理员确认草案时更新；已发布快照及历史审计保持不变。
- 不添加依赖；保留并避开当前工作区未提交改动。
- 节次、周段、地点、教师、容量、考试周及跨周期冲突均须服务端校验并原子提交。

## Review Focus

- 主任请求跨教研室课程或班级时不得泄露课程申请人，也不得保存草案；由课程板范围测试覆盖。
- 课程未申报或尚未排周段时仍须可见并可创建除教师建议外的调剂草案；由课程板/前端测试覆盖。
- 节次与房间/教师/班级在其他周期冲突时保存或管理员确认必须失败且零部分写入；由后端冲突测试覆盖。
- 保存草案后正式课表、分配和版本保持不变；退回也不改变正式安排；由事务/API 测试覆盖。
- 任一任务、排课周期或匹配候选变更后，过期草案不得确认；由指纹/revision 测试覆盖。

---

### Task 1: 教研室范围课程板与课程级草案 API

**Files:**
- Create: `backend/app/services/department_schedule_review.py`
- Modify: `backend/app/api/planning.py`
- Test: `backend/tests/test_department_schedule_review.py`

**Interfaces:**
- `department_schedule_review.visible_plans_and_tasks(db, user, anchor_plan_id)` 返回同学年学期、本室负责专业映射下的完整课程任务及只读申报摘要。
- `GET /api/planning/plans/{plan_id}/department-schedule` 返回完整课程板、课程级状态和最新草案。
- `PUT /api/planning/plans/{plan_id}/tasks/{task_id}/department-schedule-draft` 保存草案快照；`POST .../department-schedule-submit` 逐课送管理员。
- `GET /api/planning/department-schedule-reviews?plan_id=...` 返回管理员待办；管理员专用决定端点确认或退回。

- [x] **Step 1: 写后端范围和草案回归测试**
  - 主任看见其负责专业班级的全部任务，包含无申报及未排周段课程；其他教研室任务和个人资料不可见。
  - 保存草案不会更改 TeachingTask、PeriodSlot、TeachingAssignment 或正式计划 revision。
  - 其他教研室主任、教师和未授权管理员操作分别按权限拒绝。
- [x] **Step 2: 运行测试并确认按预期失败**
  - Run: `cd backend && DEBUG=false SECRET_KEY=local-test-only PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_department_schedule_review.py -v`
  - Expected: 新端点未注册，测试失败。
- [x] **Step 3: 实现范围计算和只读完整课程板**
  - 基于审核人 `offering_unit_id`、管理员维护的 `AcademicDirection.offering_unit_id`、`AcademicProgram` 与班级专业映射筛出本室负责专业班级；对该班级所有课程返回卡片，外室课程保留只读并去除申请人身份。
  - 合并 `review-overview` 中同学年学期相关周期；草案状态从不可变 `PlanningEvent` 的最新对应事件派生。
- [x] **Step 4: 实现草案存储、权限与版本保护**
  - 追加 `department_schedule_draft`、`department_schedule_submit`、`department_schedule_decision` 审计事件，不覆盖既有事件。
  - 草案包含 base task fingerprint、plan revision、拟调整周段、教师候选、room_id、slots、主任意见；验收事件绑定草案事件 ID 和当前指纹。
  - 主任只能保存/送审本室授权任务；送审后锁定该版本，管理员退回后方可再改。
- [x] **Step 5: 实现管理员待办、确认/退回 API**
  - 只允许管理员确认或退回；展示变更前后字段和冲突校验摘要。
  - 确认使用事务重新检查任务/计划版本、教师最新申报和初审、匹配资格/容量、教室、周段、节次和跨周期冲突；成功后更新 TeachingTask、PeriodSlot、TeachingAssignment 并追加决定事件。
  - 退回只追加审计事件，不更新正式排课。
- [x] **Step 6: 运行新增测试并确保通过**

### Task 2: 周段、教师、教室与周内节次的原子校验

**Files:**
- Modify: `backend/app/services/department_schedule_review.py`
- Modify: `backend/app/api/planning.py`
- Test: `backend/tests/test_department_schedule_review.py`
- Test: `backend/tests/test_review_resources.py`

- [x] **Step 1: 写失败测试**
  - 课程周段进入考试周、学生组超过每周限制、同日重复、教室容量/类型或跨周期占用冲突、教师节次/容量冲突，都拒绝草案或最终确认。
  - 失败不产生部分任务/分配/节次写入；修改其他教研室课或本人的申报须拒绝。
  - 同一接口双重提交 stale revision 或 stale task fingerprint 得到 409。
- [x] **Step 2: 运行测试确认失败**
- [x] **Step 3: 复用 `validate_spans`、`validate_tasks`、`validate_global_room`、`validate_global_student_scope`、`capacity` 与 `department_review.require_approved`，对候选副本做无写入预检。**
- [x] **Step 4: 在管理员确认事务中再次验证，再一次性应用节次和教师分配；未配置或不符合的教师候选不得成为最终分配。**
- [x] **Step 5: 运行相关后端套件并确保通过。**

### Task 3: 主任甘特图与逐门送审

**Files:**
- Modify: `frontend/src/api/planning.ts`
- Modify: `frontend/src/pages/PlanningWorkspace.tsx`
- Modify: `frontend/src/components/ReviewTimetable.tsx`
- Create or modify: `frontend/src/components/DepartmentScheduleEditor.tsx`
- Test: `frontend/tests/reviewRows.test.mjs` and focused UI/API helper tests if present

- [x] **Step 1: 为完整课程板、草案编辑和逐课送审写前端测试**
  - 默认全量显示主任负责专业班级课程；未排课程出现在“待安排”区域。
  - 编辑器包含开始/结束周、教师建议、教室、星期与节次；草案和送审状态可见。
  - 草案提示其不改变正式课表，外室卡片只读。
- [x] **Step 2: 运行相关前端测试确认失败**
- [x] **Step 3: 接入新的主任课程板 API 并移除只按申报生成甘特图的过滤。**
- [x] **Step 4: 添加可访问的课程调剂表单和状态；只有主任可对待审课程保存草案/送审，禁止管理员确认控件出现在主任视图。**
- [x] **Step 4a: 将原申报汇总中的教师初审操作移至各课程卡，不改变提交、回避和通过/退回规则。**
- [x] **Step 5: 运行前端测试。**

### Task 4: 管理员最终确认与 AI 审查摘要

**Files:**
- Modify: `frontend/src/api/planning.ts`
- Modify: `frontend/src/pages/PlanningWorkspace.tsx`
- Modify: `frontend/src/components/DepartmentAiReviewPanel.tsx`
- Test: `frontend/tests/reviewRows.test.mjs` and focused component tests if present

- [x] **Step 1: 写管理员待办及 AI 摘要展示测试**
  - 管理员查看待确认草案的变更差异、主任意见和校验摘要，可确认或退回。
  - AI 默认视图突出总体结论、风险计数、待核实项与少量课程；全文可展开；AI/规则失败有状态反馈。
  - “本学年本学期申报汇总”板块不存在。
- [x] **Step 2: 运行测试确认失败。**
- [x] **Step 3: 添加管理员最终处理面板，并在决定后刷新状态；保持其余教师申报初审组件不变。**
- [x] **Step 4: 把 AI 长文、逐教师展开解释和别名表折叠到可展开详情，默认显示关键指标与优先问题。**
- [x] **Step 5: 运行前端测试。**

### Task 5: 完整验证与本地演示

**Files:**
- Verify only; do not alter unrelated existing worktree changes.

- [x] **Step 1: 后端全量检查**
  - Run: `cd backend && DEBUG=false SECRET_KEY=local-test-only PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v`
- [x] **Step 2: 前端检查**
  - Run from `frontend`: `npm test`, `npm run build`, `npm run lint`.
- [x] **Step 3: `git diff --check` 并核对只影响设计范围文件。**
- [ ] **Step 4: 启动/重启本地服务，检查主任与管理员真实页面的角色隔离、全课程显示、草案送审、管理员确认/退回及 AI 折叠交互。**（管理员页面实测通过；演示库无主任任命，主任端仅由自动化回归覆盖。）
- [x] **Step 5: 记录服务/数据库边界、剩余警告和验证结果；不提交、不推送。**
