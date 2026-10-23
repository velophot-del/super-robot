# 学院排课平台五项改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有平台上完成方案精确绑定、Excel课程导入、课程覆盖核对、可校验的自动编排候选和教学确认/变更闭环。

**Architecture:** 增量扩展 SQLAlchemy 模型和兼容迁移，复用 `CurriculumCourse.metadata_json` 保存方案口径；管理 API 提供事务化导入、覆盖清单、候选生成和追加式运行记录。React 页面复用当前管理工作台与 Ant Design，发布继续由现有硬约束校验保护。

**Tech Stack:** FastAPI、SQLAlchemy、SQLite、React、TypeScript、Ant Design、openpyxl（项目已有）。

**Spec:** `docs/superpowers/specs/2026-10-24-academic-scheduling-improvements-design.md`

## Global Constraints

- 不安装依赖，不对演示/生产业务库运行测试或迁移。
- 保持提交、原件、审计事件、发布快照不可变。
- 教师只声明意愿；管理员仍拥有主数据、编排和发布权。
- 未知专业/年级关联不得通过子串匹配自动确认。
- 20周周期第20周为考试周，发布必须通过新版硬约束校验。

## Review Focus

- 不同方案的同编码课程学分/学时不同：由课程来源元数据保留，不覆盖公共课程行。
- 老数据仅有文本专业/年级：精确迁移或待确认，不模糊关联。
- XLSX重复编码与无效教师/课程负责人：预览定位行，确认时原子处理。
- 公共课、非排课行、占位和待核对记录：覆盖清单显式说明，不静默漏课。
- 自动排课无可行解、已有锁定项或考试周冲突：不得部分写入或绕过发布校验。

---

### Task 1: 规范培养方案主数据与课程要求

**Files:** `backend/app/models/planning.py`, `backend/app/models/course.py`, `backend/app/models/class_info.py`, `backend/app/database.py`, `backend/app/services/academic_scope.py`, `backend/app/services/course_library.py`, related tests.

- [x] 测试相同课程编码的两个培养方案可保存各自不同学分、学时和学期，且课程公共记录不被覆盖。
- [x] 测试专业相似名称不得交叉绑定；兼容迁移只精确回填并为未匹配数据保留待确认状态。
- [x] 新增专业/开课单位基础记录、课程方案关联、学制字段和 SQLite additive migration。
- [x] 上传/激活/班级关联接口以标准专业标识和入学年级值工作，保留旧字段兼容读取。
- [x] 管理页面可维护专业/开课单位和显式映射；课程编辑/列表展示开课单位与方案来源要求。
- [x] 运行目标后端测试及 schema 初始化迁移测试。

### Task 2: 普通课程 XLSX 导入预览与确认

**Files:** `backend/app/api/import_export.py`, `backend/app/utils/csv_parser.py` or focused spreadsheet parser, tests, `frontend/src/api/client.ts`, `frontend/src/pages/DataManagement/ImportPage.tsx`.

- [x] 测试多工作表表头、重复课程编码、必填学期校验及不确认不写数据库。
- [x] 添加带签名且有时限的预览令牌，令牌绑定上传内容哈希、数据类型和解析结果。
- [x] 确认接口在事务内导入，保留 CSV 入口和现有教师账户导入规则。
- [x] 前端展示新增/重复/错误预览、逐行定位和确认按钮。
- [x] 运行导入 API 与页面测试/build。

### Task 3: 周期培养方案覆盖清单

**Files:** `backend/app/api/curriculum_materials.py` or focused coverage service/API, tests, `frontend/src/api/planning.ts`, `frontend/src/components/AdminStagePlanner.tsx` or planning workspace.

- [x] 测试已生成、缺项、待核对和无班级映射等状态。
- [x] 为周期返回按方案、年级、课程行聚合的应开课程状态和原因；同名课程按来源行编码区分。
- [x] 管理界面展示覆盖总数、缺项及班级/课程来源信息。
- [x] 运行覆盖 API 与前端测试/build。

### Task 4: 新版周期自动编排候选

**Files:** `backend/app/services/stage_planning.py`, focused auto-placement service, `backend/app/api/stage_designer.py`, tests, planning API/frontend.

- [x] 测试生成仅针对已放置周段任务，周时段满足周课时、考试周、组/教师/教室冲突、容量和教室类型约束。
- [x] 生成结果完成全部校验后一次性保存并写审计事件。
- [ ] UI 展示候选预览、未排任务原因、应用候选和局部锁定；当前点击后立即计算并原子应用，尚无独立预览/对比步骤。
- [x] 对输出运行 `validate_tasks` 和教师/教室冲突校验；失败不写入。周段考试周在任务初放时校验，并由最终发布再次独立校验。
- [x] 运行调度服务/API与全量后端测试及前端 build。

### Task 5: 教师确认、调课审批与通知记录

**Files:** planning models/API/services, authorization, tests, teacher/admin pages, `PLANNING_WORKFLOW.md`.

- [x] 测试教师只能确认本人发布课表任务，不能改写发布快照或他人确认。
- [x] 调课申请、管理员批准/拒绝采用追加式不可变记录；批准创建待编排修订周期，硬冲突在该修订周期实际安排和发布时校验。
- [x] 对受影响教师产生站内通知记录；教师端展示本人确认/申请状态，管理员工作台展示待审批项。
- [x] 验证已发布快照不变且修订计划及审计事件另行保存。
- [x] 运行完整后端、前端测试、build、lint 和 `git diff --check`；更新文档说明尚未生产验收范围。
