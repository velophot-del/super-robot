import test from 'node:test';
import assert from 'node:assert/strict';

function storage(entries) {
  const data = new Map(entries);
  return { getItem: key => data.get(key) ?? null, removeItem: key => data.delete(key),
    setItem: (key, value) => data.set(key, value) };
}

test('two expired demo requests preserve the normal login', async () => {
  const { readAuthIdentity, clearRejectedIdentity, DEMO_TOKEN_KEY } = await import('../src/api/authSession.ts');
  const normal = storage([['access_token', 'normal-token']]);
  const demo = storage([[DEMO_TOKEN_KEY, 'expired-demo']]);
  const first = readAuthIdentity(true, normal, demo);
  const second = readAuthIdentity(true, normal, demo);
  assert.equal(clearRejectedIdentity(first, true, normal, demo), true);
  assert.equal(clearRejectedIdentity(second, true, normal, demo), false);
  assert.equal(normal.getItem('access_token'), 'normal-token');
  assert.equal(demo.getItem(DEMO_TOKEN_KEY), null);
});

test('stale responses cannot clear or apply over a newly selected identity', async () => {
  const { readAuthIdentity, clearRejectedIdentity, isCurrentIdentity, DEMO_TOKEN_KEY } = await import('../src/api/authSession.ts');
  const normal = storage([['access_token', 'normal-token']]);
  const demo = storage([[DEMO_TOKEN_KEY, 'old-demo']]);
  const request = readAuthIdentity(true, normal, demo);
  demo.setItem(DEMO_TOKEN_KEY, 'new-demo');
  assert.equal(clearRejectedIdentity(request, true, normal, demo), false);
  assert.equal(isCurrentIdentity(request, true, normal, demo), false);
  demo.removeItem(DEMO_TOKEN_KEY);
  normal.setItem('access_token', 'new-normal-token');
  assert.equal(isCurrentIdentity(request, true, normal, demo), false);
  assert.equal(normal.getItem('access_token'), 'new-normal-token');
});

test('production ignores demo storage and current normal failures clear only that login', async () => {
  const { readAuthIdentity, clearRejectedIdentity, DEMO_TOKEN_KEY } = await import('../src/api/authSession.ts');
  const normal = storage([['access_token', 'normal-token']]);
  const demo = storage([[DEMO_TOKEN_KEY, 'demo-token']]);
  const request = readAuthIdentity(false, normal, demo);
  assert.equal(request.source, 'normal');
  assert.equal(clearRejectedIdentity(request, false, normal, demo), true);
  assert.equal(normal.getItem('access_token'), null);
  assert.equal(demo.getItem(DEMO_TOKEN_KEY), 'demo-token');
});
