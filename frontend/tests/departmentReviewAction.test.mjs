import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as schedule from '../src/lib/departmentSchedule.ts';

test('teacher-row review uses the clicked course even before React commits selection', async()=>{
  const source=fs.readFileSync(new URL('../src/components/DepartmentScheduleBoard.tsx',import.meta.url),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
  for(const previous of [undefined,{id:101,plan_id:1}]){
    let stateIndex=0, confirmation;
    const calls=[];
    const states=[previous,undefined,undefined,false,'',false,undefined];
    const element=(type,props,...children)=>({type,props:{...props,children}});
    const React={createElement:element};
    const modules={
      react:{useState:()=>[states[stateIndex++],()=>{}],useEffect:()=>{}},
      antd:new Proxy({Modal:{confirm:value=>{confirmation=value;}},message:{success:()=>{},error:()=>{}}},{get:(target,key)=>target[key]||key}),
      '@ant-design/icons':{},
      '../api/planning':{planningApi:{decideDepartmentReview:async(...args)=>calls.push(args)}},
      '../lib/adminStageGrid':{stageLanes:()=>[]},
      '../lib/reviewRows':{reviewRows:()=>[]},
      '../lib/departmentSchedule':schedule,
    };
    const exports={};
    vm.runInNewContext(code,{exports,React,require:name=>modules[name]});
    const task={id:202,plan_id:2,plan_state:'open',can_edit_department_schedule:true,
      applicants:[{submission_id:22,selected:true,review_status:'pending'}]};
    const tree=exports.default({plan:{id:2,weeks:20},tasks:[task],busy:false,onRefresh:()=>{}});
    const table=tree.props.items.find(item=>item.key==='teachers').children;
    const row=table.props.dataSource[0];
    const actions=table.props.columns.find(column=>column.title==='审核').render(null,row);
    actions.props.children[0].props.onClick();
    await confirmation.onOk();
    assert.equal(calls[0][0],2);
    assert.equal(calls[0][1].task_id,202);
    assert.equal(calls[0][1].submission_id,22);
  }
});
