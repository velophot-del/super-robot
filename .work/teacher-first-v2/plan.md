# 教师先选课、专业匹配与阶段授课 Implementation Plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current session. Steps use checkbox (`- [ ]`) syntax for tracking. 未取得书面计划审阅结果前不实施源码。

**Goal:** 交付“待选课程库→教师意愿草稿与提交→可解释专业适配与综合推荐→有权人员审核分配→阶段课表发布”的闭环；同一教学组同周最多2门、同日仅1门。

**Architecture:** 保留React/FastAPI及资源管理基础，新增周段任务、志愿提交、评分、匹配批次和审核分配层。权限改为职能+范围的can(user, action, resource)，Debug切换仅选择预定义职能组合。课程预设周段节次供教师选择，采用规则评分与贪心/冲突回退辅助分配，最终审核确认；不以遗传算法随机指定教师、班级或时间。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、SQLite、Pydantic、React、TypeScript、Ant Design、现有openpyxl、标准库zipfile/ElementTree、unittest、Node原生测试；不新增依赖。

**Spec:** `/Users/tangwang/GPTspace/college-scheduling/analysis/2026-10-20-requirements-gap-analysis.md`及用户确认的每教学组每周最多2门规则。原始材料为`/Users/tangwang/Desktop/专业课排课平台_需求简版.md`；本计划不改写原件。此前两份设计中一致的培养方案版本、多人授课、教师草稿和课表快照要求继续适用。

## 版本关系与状态

本v2替代`2026-10-20-plan-first-workflow-plan.md`用于后续业务开发；旧文档只作历史留存，不再执行其中“固定管理员/教师角色”“后续教室遗传优化”或不含专业匹配的任务安排。当前源码只有旧资源/排课及Debug本人课表隔离；本计划中的新增模块均未实现。

## Global Constraints

- 项目：`/Users/tangwang/Desktop/AI-driven-intelligent-scheduling-platform-main`；交付说明：`/Users/tangwang/GPTspace/college-scheduling/`。
- 一期验收数据：1专业、1年级、4班、1学期。默认20周、19—20考试周，实际校历由管理员维护；不得把占位班级当成真实数据已核对。
- 教师先从待选任务库表达志愿并提交，系统只给建议，审核前不形成正式任课。已有课程与周段节次供申报，不是让教师自行填空网格。
- 全院可申报专业课不按教师部门/专业隐藏；专业方向、领域、团队用于推荐与解释，不是申报白名单。
- 同教学组同周默认1门、最多2门；同日仅1门；开放周末不提高上限。第2门允许，第3门硬拒绝。
- 时间单位为节；按周段+周内起始节与连续节数表达，1—8跨午休编号。具体日期由校历展开，冬夏作息只改变钟点显示。
- 同组课程占某日部分节次，其余节次保留不得排其他专业课；保留节次不计实际授课学时或教师课时。
- 一课多师使用实际承担周次、节次、学生组及角色关系，学生课时不因教师人数重复累计。
- 权限统一`can(user, action, resource)`，不以角色名称决定业务授权；平台管理权限不自动包含课程审核/发布权限。
- 不新增依赖、付费服务或外部AI；不改原需求文件，不删除旧数据，不自动提权旧账号，不提交/推送/公网部署。
- 未经指示不创建初始密码单、不发送邮件、不设置备份定时任务；相关流程仅在隔离测试数据中验证。
- 当前目录无Git；不初始化仓库或伪造提交。测试使用内存/临时SQLite、临时上传目录，编码UTF-8。
- 专业适配度与综合推荐分分开；缺资料显示unknown，不能编造匹配概率。六项原始满分105，归一化和规则版本可追溯。
- 任何自动匹配不能更改课程时间框架；不做自动时间排课、智能教室分配、全局最优匹配或自动化解课程冲突。

## Review Focus

1. 跨专业申报与资料缺失：不按department隐藏课程，unknown不冒充0/100；Task 4、6、8验证。
2. 同课多师与并行去重：同组同周第2门允许、第3门拒绝，同课分段不多算门数；Task 5验证。
3. 锁定/旧请求/并发：旧草稿不能覆新稿，重跑保留锁定，跨计划同一资源不能双占；Task 6、8、9验证。
4. 兼任和自审：有管理入口不等于可审自己，课程审核按课程归属；Task 2、9验证。
5. 学时/版本/材料不完整：不能用同名课程或最新文件兜底，默认精确发布、容差需明示；Task 4、5、10验证。

## 范围与依赖

Task 1—7建立资料、周段及志愿；新增Task 8计算可解释评分与匹配；Task 9审核/发布；Task 10集成验收。旧系统同名功能只能复用经验证的数据/界面，不复用随机班级教师分配。

材料上传首期支持资源CSV/XLSX、培养方案XLSX与DOCX表格预览确认。真实大纲三级降级、原学校模板Word保真、完整撤销重做、邮件/异机备份与性能专项另列验收；模板未提供前只能交付通用模板，不声称学校模板保真。以下待定项以配置草稿或明确阻断处理，不悄悄定为学院制度。

## 待校准参数与不阻塞设计的处理

| 项目 | 实施处理 |
|---|---|
| 专业与综合权重 | 六项105分仅用于标记“试算”的样例；管理员确认规则版本后才允许正式匹配批次。 |
| 志愿数量 | 模板建议3—5；可用任务不足3时提示并由计划参数降低下限，不偷偷补志愿。 |
| 学期3门计数 | 支持distinct_course与teaching_task口径；未选定计数口径不启用正式自动匹配，分别展示两项统计。 |
| 学时误差≤2 | 采用默认容差0；若学院确认容差2，必须在计划参数中显式设置并显示实际偏差，≥3始终拒绝。 |
| 审核节点 | 用可配置节点要求表达；演示单节点管理员审核显式授予review与publish，主任/秘书多节点作为同一机制的测试配置，不默认扩大学院制度。 |
| 课程与教师周上限 | 课程每周学时与教师每周20节分别配置。单师承接24节且上限20必须拒绝，不因课程上限40而放行。 |
| 初始账号授权 | 只提供显式账号授权CLI及测试，不自动升级旧普通用户；真实授权另由用户指定账号。 |

## Task 1: 修复可验证的前端基线

**Files:** Modify `frontend/src/api/client.ts`、`frontend/src/pages/Dashboard.tsx`、`frontend/src/pages/DataManagement/ClassesPage.tsx`、`TeachersPage.tsx`、`CoursesPage.tsx`、`frontend/src/pages/Scheduling/EnginePage.tsx`、`frontend/src/components/DataTable.tsx`；Test `frontend/tests/authSession.test.mjs`（已有回归保留）。

**Interfaces:** 保留Axios响应拦截器解包行为；API方法显式返回`Promise<T>`，调用点不再将`AxiosResponse`强转为业务数组。`CourseFields({form})`是独立React组件，允许在其顶层调用Form.useWatch/useEffect。

- [ ] 运行`npm test`、`npm run build`、`npm run lint`，保存已有11处TS及课程页3处Hooks错误基线，区分其他警告。
- [ ] 修正响应类型声明和未使用变量；将课程表单Hooks移入`CourseFields`，DataTable渲染其返回组件。不得关闭tsconfig规则、改成双重unknown强转或忽略Hooks错误。
- [ ] 再运行上述3个命令；通过标准为退出0，警告单独记载。
- [ ] 浏览器核对课程新增/编辑及总学时联动，确认未破坏已有表单。记录结果，不提交Git。

## Task 2: 职能+范围授权、兼任与身份绑定

**Files:** Create `backend/app/models/grant.py`、`schemas/grant.py`、`services/authorization.py`、`api/accounts.py`、`api/grants.py`、`migrations.py`、`bootstrap_admin.py`；Modify `models/user.py`、`schemas/user.py`、`services/auth.py`、`services/debug_identity.py`、`main.py`、`database.py`、`frontend/src/lib/accessPolicy.ts`、`types/index.ts`；Test `backend/tests/test_authorization.py`、`test_migrations.py`、`frontend/tests/accessPolicy.test.mjs`。

**Interfaces:** `can(user: Principal, action: Action, resource: ResourceRef) -> bool`；`require_permission(action: Action)`返回FastAPI依赖；`resolve_principal(db: Session, user: User) -> Principal`；`grant_account(db, user_id, capability, scope_kind, scope_id) -> Grant`。Principal含真实账号ID、教师绑定和服务端授予的能力范围；ResourceRef含课程归属教研室/课程ID/教师ID。缺授权默认拒绝。

**Contract:** 能力至少有`teaching`、`lead`、`review`、`publish`、`admin`；范围self/course/dept/all。`admin@all`只处理资源、账号等管理动作，审核和发布需独立授权。教师+主任账号可在同一登录切换教学/审核工作台，范围仍由服务端裁剪。普通注册不接受授权字段。

- [ ] 先写测试：teaching@self读取别人草稿403；review@dept只审本室所开课程（申请教师属其他室也允许）；admin@all没有review不能审核；同账号同时具有教学与审核能力可切工作台但不会失去范围限制。运行`DEBUG=false .venv/bin/python -m unittest discover -s tests -p test_authorization.py -v`观察失败。
- [ ] 新建grant表并添加可空唯一teacher绑定；禁用账号和首次需改密账号除规定入口外拒绝。迁移保持用户原数据，不根据旧role或账号序号自动授权；迁移后旧管理接口也使用明确授权，不保留按旧role自动放行的后门；如需保留历史只读演示须单独显式配置，不扩展到写操作。
- [ ] 所有新业务及旧管理入口调用统一授权。前端依据后端下发能力生成工作台；Debug的管理员/教师名称只是身份标签，不能成为业务if-role规则。Debug管理员预定义为admin+review+publish，Debug教师为teaching@self；普通请求不能任意提交grants给自己。
- [ ] 提供授权CLI默认dry-run，仅显式`--apply`修改指定账号，实施时不自行运行真实提权。测试账号分配授权均在临时库。
- [ ] 审计actor_key保留真实账号/教师身份和demo标记，不将演示负用户ID写入真实用户外键；授权变更只追加记录，不开放日志删除接口。
- [ ] 重跑授权/迁移/现有debug测试及前端权限测试，证明接口不能因切换工作台或传入其他资源ID越权。

## Task 3: 基础资源、教师画像与原子导入

**Files:** Modify `backend/app/models/teacher.py`、`schemas/teacher.py`、`frontend/src/pages/DataManagement/TeachersPage.tsx`；Create `backend/app/models/expertise.py`、`backend/app/services/resource_import.py`、`schemas/import_batch.py`、`api/resource_imports.py`；Modify `backend/app/api/import_export.py`、`models/classroom.py`、`schemas/classroom.py`、`frontend/src/pages/DataManagement/ImportPage.tsx`、`ClassroomsPage.tsx`、`frontend/src/api/client.ts`；Test `backend/tests/test_resource_import.py`。

**Interfaces:** `preview_resources(entity_type: str, filename: str, content: bytes, db: Session) -> ImportPreview`；`commit_resources(preview_id: str, expected_revision: int, db: Session, actor: Principal) -> ImportResult`。`POST /api/resource-imports/preview`与`POST /api/resource-imports/{id}/commit`；要求can(principal, resource.manage, resource)。预览保存在后端，确认不信任客户端替换行数据。

- [ ] 写`test_duplicate_import_does_not_overwrite`、`test_invalid_row_commits_nothing`、`test_teacher_import_forbidden`；断言已有姓名保留、失败批次新增0、教师403。运行对应unittest观察失败。
- [ ] 支持CSV UTF-8-sig，失败明确尝试GB18030并在预览标明；原件保持不变。XLSX用现有openpyxl只读读取且不执行公式。限制文件10MiB、解析行10000、压缩展开50MiB；拒绝公式及无效关键值。
- [ ] 教师新增primary_direction、expertise_tags、profile_verified、profile_revision、max_weekly_periods、max_term_courses；外部负荷按term/week/date/period保存，不能只加一个学期总数。课程团队、曾授记录保存是否已核实及来源，缺资料不能视为“不属于团队/从未教过”的已证实事实。
- [ ] 重复编号默认报错；允许显式跳过，不做静默更新。教室/实验室统一地点实体，增加设备列表及不可用日期节次；资源停用检查已发布新计划引用。上传前预览成功不等于导入成功。
- [ ] 旧CSV入口委托同一解析/校验服务，提交原子化，避免旧路径仍报告“导入成功”却未保存。
- [ ] 前端提供选择类型→文件预览/映射→确认结果，展示行错误；运行测试及前端构建，浏览器验证实验室上传与错误重试。

## Task 4: 培养方案版本和排课周期适配

**Files:** Create `backend/app/models/academic.py`、`schemas/academic.py`、`services/curriculum_import.py`、`services/curriculum_matching.py`、`api/curricula.py`、`api/terms.py`；Modify `models/__init__.py`、`database.py`、`models/class_info.py`、`schemas/class_info.py`、`models/course.py`、`schemas/course.py`；Create `frontend/src/pages/Planning/CurriculaPage.tsx`、`TermsPage.tsx`、`frontend/src/types/planning.ts`；Test `backend/tests/test_curriculum_import.py`、`test_curriculum_matching.py`。

**Interfaces:** `extract_curriculum_rows(filename: str, content: bytes) -> ExtractedTables`；`confirm_curriculum(upload_id: str, mapping: CurriculumMapping, metadata: CurriculumMetadata, db: Session) -> CurriculumVersion`；`match_curriculum(db: Session, class_id: int, term_id: int) -> CurriculumMatch`。返回`matched/missing/ambiguous`，含候选及中文原因。

**Model contract:** Major、Department、CurriculumVersion、CurriculumCourse、AcademicTerm、ClassCurriculumBinding。ClassInfo增加`major_id`及`admission_year`；旧grade文字不猜成入学年份。周期有日期范围、学年学期、18—20周、申报起止时间和班级范围。方案课程有`course_code/name/credits/total_hours/curriculum_semester`、专业课类别及先修ID。学分用Decimal/Numeric，API显式序列化为数值；旧整数课分按数值保留。

- [ ] 写`test_docx_table_preview_requires_confirmation`、`test_half_credit_preserved`，断言预览不创建课程、`credits=1.5`往返一致；写缺少/歧义匹配和逐班绑定测试。先运行对应unittest并观察失败。
- [ ] XLSX用openpyxl；DOCX用zipfile+ElementTree提取表格，保留表号/行号，处理空/合并单元格时保留来源而非猜补。DOCX总展开不超50MiB，不落盘解压路径；扫描PDF返回明确不支持说明，不假装完成OCR。管理员映射课程字段、确认专业/届次/版本后才保存审核版。
- [ ] 文件保存于配置`UPLOAD_DIR`按UUID生成名称，原文件名只作元数据；原件下载检查can(principal, material.read, resource)，禁止路径穿越与覆盖；记录SHA256。测试用临时目录，不写真实归档。
- [ ] 课程版本增加direction、required_expertise_tags、owning_department_id及profile_verified，使用管理员维护的标签字典与同义词映射。生效课程内容只读，启用/替代状态另表保存；派生修订保留原引用。
- [ ] 按专业、入学届次、培养学期和明确绑定版本匹配；多有效版本必须管理员选定绑定。周期仅生成专业课，公共课另作固定占用输入。
- [ ] 测试确认相同课程两班各有完整来源、不同专业同名课程不串用、缺失入学年级不兜底。前端显示匹配预览、字段错误和原件版本，不将未审核提取结果发布。

## Task 5: 阶段任务、周段编排与每周2门硬约束

**Files:** Create `backend/app/models/teaching.py`、`schemas/teaching.py`、`services/plan_generation.py`、`services/plan_validation.py`、`api/teaching_plans.py`、`frontend/src/pages/Planning/PlanPage.tsx`、`frontend/src/components/MeetingEditor.tsx`；Modify `models/__init__.py`、`main.py`、`frontend/src/api/client.ts`；Test `backend/tests/test_plan_generation.py`、`test_plan_validation.py`。

**Model contract:** PlanRevision(term_id, revision, source_hash, state)、TeachingTask(class_group_id, curriculum_course_id, source_snapshot, start_week, end_week, required_hours)、TeachingUnit(task_id, student_scope, required_teachers, role_slots)、PeriodSlot(unit_id, day_of_week, start_period, period_count, phase, room_id可空, room_locked)、StudentGroup及学生稳定编号关联、TimePeriod、CalendarDay、FixedOccupancy、Occupancy。PeriodSlot为唯一持久化的周内排课来源，实际日期课次和活动占用均由周段+校历派生；不再维护另一份可直接编辑的PlannedMeeting作为第二真源。不修改旧课表条目为假教师占位。

**Interfaces:** `preview_generation(db: Session, term_id: int) -> GenerationPreview`；`generate_plan(db: Session, term_id: int, expected_term_revision: int, actor: Principal) -> PlanRevision`；`validate_plan(db: Session, revision_id: int, phase: Literal['application','publication']) -> ValidationReport`。报告`code/slot_ids/actual_dates/message`；`PUT /api/plans/{id}/slots/{slot_id}`带expected_revision修改周内节次/地点，要求can(principal, plan.manage, resource)；课程周段修改单独更新TeachingTask并完整复验。

- [ ] 写测试：两个班同课各需32学时生成后各32；教师栏无分配记录；再次同输入生成仍同一修订且不增加任务；日期缺失时预览列问题且不发布；`1.5`学分不丢失。先运行观察失败。
- [ ] 管理员补录课程边界、具体日期和节次集合；缺少时间时可以查看课程清单但生成发布不补造日期。预设输入满足后生成计划，名称/学分/学时写入来源快照。
- [ ] 支持单元分段、学生分组、同堂角色，可组合；2位同堂教师上2节学生记2学时；两组各2节，每组各记2，分组名单缺失按全班占用并提示。
- [ ] 新增`test_two_courses_allowed_third_rejected`：同教学组W1—W4的课程A周一至三、B周四至五允许；W3加入C必须拒绝。新增`test_same_day_reserved_for_one_course`：A周一只用1—4节，B周一第5节仍拒绝；A保留节次不计学生或教师实际学时。
- [ ] `validate_stage_limits(tasks: list[TeachingTask], calendar: list[CalendarDay]) -> ValidationReport`按每教学组每周不同课程标识去重，max_concurrent_courses=2。默认1门是偏好不是硬拒绝；同课分段、多教师不多算门数；周末开放不改上限。
- [ ] 编辑器保存start_week/end_week及每周day/start_period/period_count，期末尾段可有tail_weekly_hours和tail_weeks；只在校历展开时形成actual_date，冬夏时间表不改原节次。三态网格分别显示实授、该课保留、可用，核算条常驻；不得出现附件列明的禁词文案。
- [ ] 活动占用按resource_type/resource_id/actual_date/period_id唯一，跨计划同资源统一校验，历史快照不写入活动占用。同组同日归属及同周2门检查在取得数据库写锁后复验；并发添加两个不同课到同日只能一个成功。
- [ ] 校验实际教学日、全部节次、学时完整、分组学生冲突、先修循环和日期关系、地点容量设备/停用/固定占用。location候选API返回不可用原因，管理员手选后`room_locked=true`，不能被后续自动安排覆盖。
- [ ] 申报发布检查时间/任务/名额/学时完整，允许教师和地点待定；正式发布额外要求所有教师、地点齐全。只读教师计划API只提供已发布申报版本。
- [ ] 运行生成/校验测试和前端构建；浏览器核对课程、学时、学分、日期节次、待分配教师，及手选教室/实验室。

## Task 6: 教师草稿、提交快照与版本冲突

**Files:** Create `backend/app/models/preference.py`、`schemas/preference.py`、`services/teaching_preference.py`、`api/teaching_preferences.py`；Modify `models/__init__.py`；Test `backend/tests/test_teaching_preferences.py`。

**Interfaces:** `save_draft(db: Session, actor: Principal, term_id: int, data: DraftWrite) -> DraftResponse`；`submit_preferences(db: Session, actor: Principal, term_id: int, expected_revision: int) -> SubmissionResponse`。`GET/PUT /api/my/teaching-preferences/{term_id}/draft`、`POST .../submit`、`GET .../submissions`；不接受客户端指定teacher_id。

**Contract:** DraftWrite含`expected_revision`、`plan_revision`、有序`unit_id/role_slot_id`清单；提交创建不可变批次快照。草稿与最新已提交意愿分开保存，未再次提交的草稿不覆盖管理员看到的提交内容。

- [ ] 写`test_draft_survives_new_session`、`test_teacher_cannot_read_other_draft`、`test_stale_save_returns_409`、`test_submission_is_immutable`、`test_deadline_checked_server_side`；字面断言草稿2项、排序[2,1]、越权403、旧修订409。先运行失败。
- [ ] 服务端按已发布计划、授课角色和教师本人验证；不按所属专业或教研室禁止申报。候选志愿之间时间重叠可提示，既有任务冲突供匹配阶段硬校验；先申报不等于占名额。使用服务器Asia/Shanghai时间判申报期，过期拒绝提交。
- [ ] 计划日期或工作量更新后，旧提交显示需重新确认；管理员不能据旧计划审核。最终分配存在后不允许教师自行撤销任课关系。
- [ ] 事务保存、唯一教师周期草稿及乐观版本；乱序保存请求返回409和最新版本，不执行最后到达覆盖。重跑测试并检查测试数据库无半写入。

## Task 7: 教师图形化预选与专属导航

**Files:** Create `frontend/src/pages/Teaching/SelectionPage.tsx`、`SubmissionsPage.tsx`、`MyTimetablePage.tsx`、`frontend/src/components/TeachingTimeline.tsx`、`PreferenceBasket.tsx`、`frontend/src/api/planning.ts`、`frontend/tests/preferenceSelection.test.mjs`；Modify `frontend/src/App.tsx`、`components/AppLayout.tsx`、`pages/DebugPage.tsx`、`contexts/AuthContext.tsx`、`types/planning.ts`。

**Interfaces:** `planningApi.myPlan(termId: number): Promise<PlanResponse>`、`loadDraft(termId: number): Promise<DraftResponse>`、`saveDraft(termId: number, data: DraftWrite): Promise<DraftResponse>`、`submit(termId: number, revision: number): Promise<SubmissionResponse>`。选择操作纯函数`togglePreference(items: PreferenceItem[], item: PreferenceItem): PreferenceItem[]`和`movePreference(items, itemKey, delta)`放在`frontend/src/lib/preferenceSelection.ts`供界面及原生测试复用。

- [ ] 先写原生测试，断言重复点选取消、同堂角色/分组标识不混淆、按钮排序结果[2,1]和移到边界不丢项；运行`npm test`观察新用例失败。
- [ ] 页面显示已有课程与预设时间，不允许拖动课程更改时间。卡片显示学分、总学时、班级/组、阶段/角色、地点待定状态及冲突提示；标明“专业适配度”和证据完整度，未确认画像显示资料不足。学期时间轴展开周课表，桌面5×8为首期填报界面，不承诺移动端填报。
- [ ] 点选加入侧栏草稿；用串行保存并显示状态防止未返回修订被下一请求覆盖。发生409先保留本地未保存意愿、展示冲突并允许刷新核对，不静默丢弃或覆盖服务端内容。
- [ ] 草稿载入完成前禁用提交；提交前汇总本人承担范围、志愿和学时。按钮排序作为拖动替代；保存失败有可见重试，不显示已保存。
- [ ] 导航按can动作与范围展示：teaching工作台有可申报、草稿、申报结果、本人课表、通知；review工作台按课程归属提供待办；admin工作台管理资料。兼任默认我的教学任务，可切工作台不重登；直接输入无权路由仍拒绝。Debug进入对应预定义职能组合，沿用缓存清理与令牌保护。
- [ ] 运行`npm test/build/lint`；浏览器验证教师A预选保存、刷新恢复、提交；切教师B看不到A草稿；切回A状态正确。

## Task 8: 专业适配评分、候选排序与锁定重跑

**Files:** Create `backend/app/models/matching.py`、`schemas/matching.py`、`services/teacher_course_matching.py`、`api/matching.py`、`frontend/src/pages/Planning/MatchingPage.tsx`；Modify `frontend/src/api/planning.ts`、`frontend/src/types/planning.ts`；Test `backend/tests/test_teacher_course_matching.py`。

**Interfaces:** `score_candidate(teacher: TeacherProfile, course: CourseProfile, preference: PreferenceSnapshot, capacity: CapacitySnapshot, rule: MatchRule) -> CandidateScore`；`run_matching(db: Session, plan_id: int, expected_revision: int, actor: Principal) -> MatchRun`；`normalize_total(raw: Decimal, maximum: Decimal) -> Decimal`。CandidateScore含professional_fit(0—100或null)、raw_total(0—105或null)、normalized_total、六项components/evidence、completeness、eligible和rejection_reasons。

**Contract:** 基准试算规则团队40、方向20、领域15、曾授15、志愿10/7/5/3/1、剩余容量0—5，最大105；专业分仅方向+领域除以35归一化。标准化总分=raw_total/105×100，不命名为专业能力概率。规则要有revision及confirmed标记，未确认只能试算不能最终分配。

- [ ] 先写`test_professional_score_separate_from_total`、`test_unknown_profile_not_zero`、`test_department_not_a_whitelist`、`test_high_score_cannot_bypass_capacity`、`test_rerun_keeps_locked_assignments`。字面样例：方向20+领域15→专业100；归一化函数输入原始105、满分105→100；方向资料缺失→professional_fit=null；负荷12+外部8=20，再加1→eligible=false。先运行对应unittest观察失败。
- [ ] 方向按经确认的标准方向匹配；领域按命中课程required_tags的比例计算该15分。没有required_tags或教师画像未核实则标unknown，不填0/100。团队/曾授数据只有来源已审核且为空时才可确定为0；证据不足候选单列待核实，不与资料齐全候选混排成虚假准确分数。
- [ ] 剩余容量分采用显式规则`5×clamp((limit−assigned−external−candidate)/limit,0,1)`，limit=0视为不可承接；候选时间按实际授课周次与节次计，容量分逐周计算后取候选占用周中的最紧一周，不能只看学期平均。每日8节、每周上限及学期门数阈值均为硬约束，系数折算不能减少实际占用。学期门数按计划确认的计数口径计算。
- [ ] 仅对已提交快照运行确定性贪心建议，受限任务先处理，候选按归一化分、志愿序、稳定teacher_id打破平分；发生资源冲突回退至下一可行候选，未匹配列缺口。保存输入快照、规则、排除原因、候选顺序及建议；不声称全局最优。
- [ ] 每次运行新MatchRun；重跑固定已锁定分配，若锁定已与新输入冲突则中止并解释，不能静默解锁。输入或规则变更使旧批次过期，审核旧批次返回409。
- [ ] 匹配工作台显示专业适配与综合推荐两栏，六项可展开、来源可查，教师仅看本人结果，有权审核人看范围内任务。运行测试并手算核对105分及外部课时样例。

## Task 9: 按职能范围审核、多人分配与正式发布

**Files:** Create `backend/app/models/assignment.py`、`schemas/assignment.py`、`services/teaching_assignment.py`、`api/teaching_review.py`、`frontend/src/pages/Planning/ReviewPage.tsx`；Modify `services/plan_validation.py`、`models/__init__.py`、`frontend/src/api/planning.ts`；Test `backend/tests/test_teaching_review.py`。

**Interfaces:** `review_submission(db: Session, actor: Principal, data: ReviewWrite) -> ReviewResponse`；`publish_timetable(db: Session, actor: Principal, plan_id: int, expected_revision: int) -> PublishedTimetable`；`get_my_timetable(db: Session, actor: Principal, term_id: int) -> list[MeetingResponse]`。ReviewWrite包含submission_revision、plan_revision、match_run_revision及逐名额`teacher_id/decision/reason`，不是只审批课程ID。

- [ ] 写测试：多人争同一名额第二次确认409；两位同堂教师同时占用；平行组无交集时允许并行；先修冲突阻止分配；旧提交审核409；无review职能或超范围审核403，自审应上提且不能进本人普通待办。先运行失败。
- [ ] 数据库约束固定名额不可重复确认，同堂可有多个不同角色名额；一事务校验所有教师、地点和学生范围后更新分配、任务版本、审计和站内通知。
- [ ] SQLite操作在读取业务状态前取得写事务，两个独立连接竞争同名额必须只有一个成功；不以进程内锁代替数据库并发保证。审核无效不留下部分名额或通知。
- [ ] 审核链存节点动作+范围而非固定账号，按课程归属匹配review@dept或review@all；自己申报默认回避上提，无可用上级时只有显式配置允许的自审例外才可记录self_review标记，并在发布页逐项确认。同账号连续命中两节点标记合并，不冒充双人审核。
- [ ] 有权审核界面按任务/段/组/角色展示志愿、专业分/综合分及依据、已确认学时和时间冲突，可确认、退回或附说明不分配；无人申报标识并支持管理员指定。所有操作带expected_revision；改选非首位候选记录原因并再次校验，不把系统建议自动确认为任课。
- [ ] 正式课表保存发布修订快照，教师和地点缺失、未审、自审例外未确认、输入/匹配批次过期或硬冲突不允许发布；本人课表只返回实际参与记录，导出绑定周期和版本并完整读取所有数据，不混合旧排课版本。
- [ ] 运行审核及统一校验测试；浏览器验证提交→管理员审核→教师结果和课表同步，刷新结果仍保留。未实现调课时不显示可操作的假按钮。

## Task 10: 集成演示、资料及验收记录

**Files:** Create `backend/tests/test_planning_workflow.py`、`backend/scripts/seed_planning_demo.py`、`docs/PLANNING_WORKFLOW.md`；Modify `AGENTS.md`、`DEBUG.md`、`frontend/src/pages/DebugPage.tsx`、`main.py`。测试样例由脚本在临时目录生成，不复制真实师生数据。

**Interfaces:** `seed_demo(db_url: str, expected_demo_db_url: str) -> DemoSummary`，只允许与显式demo配置匹配的独立数据库；保留现有资源，用唯一前缀添加演示数据，不删除或覆盖用户编辑。

- [ ] 写完整API集成测试：主验收为2026级视觉传达1专业1年级4班第2学期；另用隔离数据测试跨专业申报和不同方案版本，不冒称主验收含全院数据；至少1项分段、1项分组、1项同堂任务，按真实各组学时配置。教师2份独立草稿、管理员不同审核结果，发布后逐学生组学时正确。
- [ ] 验证教师对所有旧数据写入口403，关闭Debug后demo token401，真实教师绑定与职能授权后仍可正常登录；公共匿名健康接口保留。
- [ ] 执行后端完整unittest、前端`npm test`、`npm run build`、`npm run lint`，要求退出0；不通过就记录具体失败并修复相关问题，不宣称全通过。
- [ ] 浏览器使用Debug分别演示管理员上传/周期/生成/地点、教师预选草稿/提交、管理员审核、教师结果；检查桌面和窄屏基本操作、空状态、失败反馈与键盘操作。
- [ ] 运行数据迁移在演示副本，记录旧行数及哈希边界；真实数据未验证不得声称全院可上线。启动命令和测试命令更新AGENTS，用户流程写入PLANNING_WORKFLOW。
- [ ] 保存交付清单：实际改动文件、通过测试数、浏览器验证范围、导入格式与未支持资料、待办子项目。不提交Git、不部署、不安装依赖。

## 后续子项目与明确边界

1. 真实文档和模板专项：大纲三级降级定义、原校docx/xlsx渲染预演和版式比对。材料未提供不承诺模板保真；发生新依赖/外部服务需求先说明确认。
2. 课表编制增强：20步撤销重做、周段双栏与总表切换的完整验收、缺口二轮与异议；不得用占位按钮宣称已完成。
3. 正式发布后的教师直接调课：此前确认的本人课程日期范围内调整及同堂直接生效保留。若附件的新审核节点改变学期中调整制度，另作明确设计，不把选课审核直接套入调课。
4. 运维和全院推广：性能p95<200ms、50人填报须定环境数据并实测；异机备份/邮件不在本轮授权中执行。
5. 旧遗传排课仅保留为历史演示和代码参考；新主菜单不调用它，不安排后续“遗传教室分配”，除非用户另行明确恢复该研究目标。

## v1到v2变更与自审

| 原计划 | 新计划 |
|---|---|
| 固定管理员/教师角色 | can(user, action, resource)，教学/审核/管理可兼任、带范围。 |
| 主要完成教师草稿后直接审核 | 新增独立Task 8专业评分与综合推荐，保存证据与匹配批次，审核人决定。 |
| 学期任务约束未包含并行上限 | Task 5硬约束同组同周≤2、同日1门，保留格不计实际学时。 |
| 部门匹配容易限制课程池 | 课程池不按专业教研室隐藏，专业画像用于推荐，不作白名单。 |
| 后续教室遗传优化 | 新主线不做自动时间排课和智能教室分配，地点手选。 |
| 权重未定义或总分混用 | 专业分/综合分分开，105分归一化，缺资料unknown，规则试算和确认分开。 |

覆盖核对：画像资源Task 3、课程方案Task 4、阶段限额Task 5、教师先申报Task 6—7、专业匹配Task 8、范围审核与发布Task 2/9、全链路Task 10。Review Focus五类均有对应行为测试。新增接口、模型和测试均是后续实施目标，不是已存在文件清单。

本v2为修订后的书面实施计划，待审阅后执行。推荐当前会话主代理顺序实施；不重复询问已确认的每周2门、同日1门或教师先申报规则。不提交、不安装依赖、不部署。
