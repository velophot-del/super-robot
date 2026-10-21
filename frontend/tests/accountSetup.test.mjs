import test from 'node:test';
import assert from 'node:assert/strict';
import { requiresAccountSetup } from '../src/lib/accessPolicy.ts';
test('account remains locked until both password and profile steps are complete',()=>{
 assert.equal(requiresAccountSetup({password_change_required:true,profile_required:true}),true);
 assert.equal(requiresAccountSetup({password_change_required:false,profile_required:true}),true);
 assert.equal(requiresAccountSetup({password_change_required:true,profile_required:false}),true);
 assert.equal(requiresAccountSetup({password_change_required:false,profile_required:false}),false);
 assert.equal(requiresAccountSetup(null),false);
});
