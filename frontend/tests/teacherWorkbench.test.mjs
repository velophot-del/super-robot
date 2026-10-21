import test from 'node:test';
import assert from 'node:assert/strict';

test('selection workbench excludes closed, expired, matched and published cycles', async () => {
  const { openSelectionPlans } = await import('../src/lib/teacherWorkbench.ts');
  const now = Date.parse('2026-10-21T00:00:00Z');
  const plans = ['open', 'draft', 'matched', 'published'].map((state, id) => ({id, state, deadline:'2026-10-22T00:00:00Z'}));
  plans.push({id:9,state:'open',deadline:'2026-10-21T00:00:00Z'});
  plans.push({id:10,state:'open',deadline:'invalid'});
  assert.deepEqual(openSelectionPlans(plans,now).map(p=>p.id),[0]);
});

test('current semester remains default even when only historical timetables exist', async () => {
  const { timetablePeriods, periodKey } = await import('../src/lib/teacherWorkbench.ts');
  const current={academic_year:'2026—2027',academic_term:1};
  const batches=[{plan:{academic_year:'2025—2026',academic_term:2}}, {plan:{academic_year:'2025—2026',academic_term:2}}];
  const periods=timetablePeriods(batches,current);
  assert.equal(periodKey(periods[0]),'2026—2027:1');
  assert.equal(periods.length,2);
  assert.equal(batches.filter(b=>periodKey(b.plan)===periodKey(periods[0])).length,0);
});
