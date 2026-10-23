import test from 'node:test';
import assert from 'node:assert/strict';
import { filterCourses, courseFilterOptions, loadAllCourses, GRADE_TABS, inGrade } from '../src/lib/courseFilters.ts';
const courses=[{id:1,department:'设计',cohort:'2025',course_type:'专业课',course_nature:'必修课'},{id:2,department:null,course_type:'综合实践课',course_nature:'任选课'}];
test('cohort filters and combined dimensions match one source, preserve unset courses',()=>{
 for(const [filters,count] of [[{department:'设计'},1],[{cohort:'2025'},1],[{department:'设计',cohort:'2026'},0],[{category:'任选课',cohort:'2025'},0],[{department:'设计',cohort:'2025',category:'必修课',course_type:'专业课'},1],[{cohort:'__unset__'},1],[{course_type:'综合实践课'},1],[{},2]]) assert.equal(filterCourses(courses,filters).length,count);
 const options=courseFilterOptions(courses);
 assert.deepEqual(options.department,['设计']);assert.deepEqual(options.cohort,['2025']);
});
test('load complete catalog beyond 500 rows',async()=>{
 const all=Array.from({length:1001},(_,id)=>({id}));
 const rows=await loadAllCourses(async p=>all.slice(p.skip,p.skip+p.limit),{search:'测试'});
 assert.equal(rows.length,1001);assert.equal(rows.at(-1).id,1000);
});

test('manual course can combine its department with unset source dimensions',()=>{
 assert.equal(filterCourses([{department:'设计',course_type:'选修'}],{department:'设计',cohort:'__unset__',category:'__unset__'}).length,1);
});

test('grade tabs map curriculum semesters and never hide unset semesters',()=>{
 assert.deepEqual(GRADE_TABS.map(tab=>[tab.label,tab.semesters]),[['大一',[1,2]],['大二',[3,4]],['大三',[5,6]],['大四',[7,8]]]);
 assert.equal(inGrade(1,'freshman'),true);
 assert.equal(inGrade(3,'freshman'),false);
 assert.equal(inGrade(4,'sophomore'),true);
 assert.equal(inGrade(7,'senior'),true);
 assert.equal(inGrade(null,'junior'),true);
 assert.equal(inGrade(undefined,'senior'),true);
 assert.equal(inGrade(9,'senior'),true);
 assert.equal(inGrade(9,'freshman'),false);
});
