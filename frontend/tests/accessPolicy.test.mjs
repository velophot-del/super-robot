import test from 'node:test';
import assert from 'node:assert/strict';

test('teacher workspace has only its own timetable and no management access', async () => {
  const { navigationKeys, canManage } = await import('../src/lib/accessPolicy.ts');
  assert.deepEqual(navigationKeys('teacher'), ['/timetable']);
  assert.equal(canManage('teacher'), false);
  assert.equal(canManage('admin'), true);
  assert.ok(navigationKeys('admin').includes('data'));
});

test('new workspace checks explicit capabilities, never an admin label', async()=>{
  const {can}=await import('../src/lib/accessPolicy.ts');
  assert.equal(can({role:'admin',grants:[]},'admin'),false);
  const user={grants:[{capability:'teaching',scope:'self',scope_id:''},{capability:'review',scope:'dept',scope_id:'Design'}]};
  assert.equal(can(user,'teaching'),true);assert.equal(can(user,'review'),true);assert.equal(can(user,'publish'),false);
});

test('department head capability exposes review navigation but not admin or publication', async()=>{
  const {can}=await import('../src/lib/accessPolicy.ts');
  const user={grants:[{capability:'teaching',scope:'self',scope_id:''},{capability:'lead',scope:'dept',scope_id:'Design'}]};
  assert.equal(can(user,'teaching'),true);
  assert.equal(can(user,'review'),true);
  assert.equal(can(user,'admin'),false);
  assert.equal(can(user,'publish'),false);
});
