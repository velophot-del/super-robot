# Mobile Selection Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 手机选课时可直接看到并点击甘特图课程。

**Architecture:** 复用 Ant Design 响应式断点和 Drawer。手机将固定信息合并为80px一列，桌面仍显示三列；共享课表组件沿用已有回调。

**Tech Stack:** React, TypeScript, Ant Design, existing CSS.

**Spec:** 本轮用户确认的方案：合并固定列、抽屉导航、横向滑动提示、详情预选，桌面布局不变。

## Global Constraints
- 不新增依赖，不提交或推送，不修改后端或业务规则。
- 保留草稿、提交、只读课表及考试周逻辑。

## Review Focus
- 360/400px宽度下固定列仅80px，课程可见且详情可点击。
- 长班级、专业信息可查看完整内容。
- 导航打开不挤压课表，选菜单后关闭。
- 详情预选继续调用原有保存流程，截止/只读限制保留。
- 桌面三列、复选框及正常导航保持可用。

## Task 1: 手机布局
- [x] 修改 AppLayout.tsx：窄屏使用 Drawer，复用菜单权限和导航。
- [x] 修改 StageSelectionTable.tsx：窄屏合并固定列，保留64px每周宽度和现有课程回调。
- [x] 修改 index.css 和 TeacherSelectionPage.tsx：滑动提示、触控标题、详情宽度及推荐换行。
- [x] 运行 frontend 的 npm test、npm run build、npm run lint。
- [x] 浏览器检查手机与桌面布局、导航、课程详情和演示预选；不提交选课。

## Verification
- Frontend: 39/39 tests passed, build passed, lint passed with 5 existing warnings; existing bundle size warning remains.
- Browser: 400px and 360px viewport; fixed column measured 80px, no page overflow, sidebar absent; horizontal scroll and full class information dialog verified.
- Mobile course detail opened and preselection saved; test selection removed, original empty draft content restored; no submission.
- Navigation opens as overlay and closes after selecting menu; desktop restored three headers and four checkboxes.
- Independent read-only review found no important defects. No dependencies installed, commits or pushes.
- Ruling: use Ant Design md breakpoint (768px) for table and navigation; preserve existing 760px filter CSS. Pure layout changes validated in browser rather than adding source-mirroring tests.
