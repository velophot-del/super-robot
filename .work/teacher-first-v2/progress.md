# SDD ledger — plan: /Users/tangwang/GPTspace/college-scheduling/plans/2026-10-20-teacher-first-workflow-plan-v2.md

User approved code execution after the v2 plan. Work occurs in the existing unpacked project; no Git exists, no worktree or commits will be created. Preserve all existing data.

Ruling: Implement the teacher-first vertical workflow first, then extend supporting imports — the actual requested deficiency is absent selection/matching/review; deliver demonstrable real APIs and UI rather than another design.

Ruling: Add separate profile/grant/planning tables instead of altering old resource columns wherever possible — preserve existing demo edits and avoid destructive SQLite migrations. No dependencies are added.

Ruling: Keep unsupported actual document/OCR/template fidelity explicit; do not claim the entire college deployment verified from demo data.

Tasks: 1 baseline pending; 2 grants pending; 3 profiles/imports pending; 4 curricula pending; 5 stage plans pending; 6 preferences pending; 7 UI pending; 8 matching pending; 9 review/publish pending; 10 verification pending.

2026-10-20 implementation checkpoint: core capabilities/scopes, profile editing, immutable curriculum versions/import activation, task generation, stage grid, preference draft/submission, explained six-part match scores, capacity-gated manual review, publication and snapshot XLSX export implemented. Original frontend build blockers fixed. Backend/full frontend verification recorded in PLANNING_WORKFLOW.md. Reviewer found duplicate teacher lock and missing-room open deadlock; both reproduced then fixed; cross-published student constraints added. Full v2 remains incomplete: see explicit remaining list in PLANNING_WORKFLOW.md. No claim of all ten tasks complete. Demo DB backed up before additions; only fictional new planning records seeded. No production rollout, commit, dependencies or real-account grants changed.

Final check: backend 17 tests PASS; frontend 6 tests PASS; tsc/Vite build PASS; oxlint exit0, 7 warnings. Live teacher UI shows saved preference and no data-management menu. Backend restarted with final fixes on port8000.
