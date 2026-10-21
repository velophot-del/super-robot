import test from 'node:test';
import assert from 'node:assert/strict';
import {academicCalendar,suggestedMonday} from '../src/lib/academicCalendar.ts';
test('opening date suggests its Monday, including Sunday, leap days and year boundaries',()=>{
 assert.equal(suggestedMonday('2028-02-29'),'2028-02-28');
 assert.equal(suggestedMonday('2027-01-03'),'2026-12-28');
 assert.equal(suggestedMonday('2027-02-01'),'2027-02-01');
 assert.equal(suggestedMonday('2027-02-29'),undefined);
 const rows=academicCalendar('2028-02-28');
 assert.equal(rows.length,20);assert.equal(rows[0].end,'2028-03-05');
 assert.equal(rows[19].start,'2028-07-10');assert.equal(rows[19].exam,true);
 const short=academicCalendar('2028-02-28',18);
 assert.equal(short.length,18);assert.equal(short[17].exam,true);assert.equal(short[16].exam,false);
 assert.deepEqual(academicCalendar('2028-02-29'),[]);
});
