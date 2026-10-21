import { useRef, useState } from 'react';
import { Alert, Button, InputNumber, Select, Space, Tag, Typography } from 'antd';
import { planningApi } from '../api/planning';
import { estimateWorkload, workloadParameterRows } from '../lib/workloadEstimate';
import type { EstimateInput } from '../lib/workloadEstimate';
import HelpTip from './HelpTip';

const kindNames:Record<string,string>={shared:'多人授课',design:'毕业设计',thesis:'毕业论文',ambiguous:'毕业设计（论文）'};
const formulaHelp=<>
  <div>预估课时统一按 25 人基数 1 计算，不含班级实际人数系数。</div>
  <div>实际课时量：有周内节次时按真实周次（含尾周）统计；无节次时按方案周课时与尾周课时还原。</div>
  <div>多人授课按本人授课周数占课程周数的比例分配。</div>
  <div>毕业设计每生 12 课时，毕业论文每生 8 课时。</div>
  <div>真实工作量在管理员确认授课班级和人数后按实际人数系数计算，选课阶段不显示。</div>
</>;

export default function WorkloadEstimatePanel({plan,disabled}:{plan:any;disabled:boolean}){
  const [inputs,setInputs]=useState<Record<number,EstimateInput>>(plan.workload_estimates||{});
  const [dirty,setDirty]=useState<Record<number,boolean>>({}),[saving,setSaving]=useState<Record<number,boolean>>({}),[errors,setErrors]=useState<Record<number,string>>({});
  const locks=useRef(new Set<number>());
  // 只有多人授课需要按本人上课周分配；毕业设计/论文按本人指导人数计算。
  const rows=workloadParameterRows(plan.tasks,plan.draft.task_ids);
  const estimate=estimateWorkload(plan.tasks,plan.draft.task_ids,inputs);
  const change=(id:number,field:keyof EstimateInput,value:any)=>{
    setInputs(old=>({...old,[id]:{...old[id],[field]:value}}));
    setDirty(old=>({...old,[id]:true}));
  };
  const save=async(id:number)=>{
    if(!dirty[id]||locks.current.has(id)||disabled)return;
    locks.current.add(id);setSaving(old=>({...old,[id]:true}));setErrors(old=>({...old,[id]:''}));
    try{
      const value=await planningApi.saveWorkloadEstimate(plan.id,id,{...inputs[id],revision:inputs[id]?.revision??0});
      setInputs(old=>({...old,[id]:value}));setDirty(old=>({...old,[id]:false}));
    }catch(e){setErrors(old=>({...old,[id]:e instanceof Error?e.message:'保存失败，请重试'}));}
    finally{locks.current.delete(id);setSaving(old=>({...old,[id]:false}));}
  };
  return <div style={{padding:16,margin:'16px 0',border:'1px solid #d9d0f5',borderRadius:8,background:'#faf8ff'}}>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12,flexWrap:'wrap'}}>
      <Space wrap><Typography.Text strong>授课参数与预估课时</Typography.Text><Tag>按25人基数</Tag><Tag color="purple">预估合计 {Number(estimate.total.toFixed(2))} 课时</Tag>{estimate.pending>0&&<Tag color="orange">{estimate.pending}门待补充</Tag>}</Space>
      <HelpTip title={formulaHelp}/>
    </div>
    {estimate.rows.length>0&&<Space wrap style={{marginTop:8}}>
      {estimate.rows.map(row=><Tag key={row.id}>{row.task?.name||`课程${row.id}`}：{row.hours===null?'待补充':`${Number(row.hours.toFixed(2))}课时`}</Tag>)}
    </Space>}
    {rows.map(row=>{
      const value=inputs[row.id]||{},locked=disabled||saving[row.id];
      return <div key={row.id} style={{borderTop:'1px solid #e8e3f1',padding:'10px 0'}}>
        <Space wrap><Typography.Text strong>{row.task?.name||`课程任务${row.id}`}</Typography.Text><Typography.Text type="secondary">{row.task?.group}</Typography.Text><Tag>{kindNames[row.kind]||row.kind}</Tag></Space>
        <Space wrap style={{display:'flex',marginTop:8}}>
          {row.kind==='ambiguous'&&<label>指导类型 <Select aria-label={`指导类型 ${plan.id} ${row.id}`} disabled={locked} value={value.guidance_kind??undefined} style={{width:150}} placeholder="请选择类型" options={[{value:'design',label:'毕业设计'},{value:'thesis',label:'毕业论文'}]} onChange={v=>change(row.id,'guidance_kind',v)}/></label>}
          {row.kind==='shared'?<label>本人授课周数 <InputNumber aria-label={`本人授课周数 ${plan.id} ${row.id}`} min={0} max={plan.weeks} precision={0} value={value.weeks} disabled={locked} onChange={v=>change(row.id,'weeks',v)} onBlur={()=>void save(row.id)}/></label>
            :<label>本人指导人数 <InputNumber aria-label={`本人指导人数 ${plan.id} ${row.id}`} min={0} max={10000} precision={0} value={value.guidance_students} disabled={locked} onChange={v=>change(row.id,'guidance_students',v)} onBlur={()=>void save(row.id)}/></label>}
          <Button size="small" loading={saving[row.id]} disabled={disabled||!dirty[row.id]} onClick={()=>void save(row.id)}>保存参数</Button>
          <Typography.Text type="secondary">{saving[row.id]?'保存中':dirty[row.id]?'本项输入尚未保存':value.revision?'参数已保存':'请填写本人承担参数'}</Typography.Text>
        </Space>
        {errors[row.id]&&<Alert type="error" showIcon title={errors[row.id]} style={{marginTop:8}}/>}
      </div>;
    })}
    {!rows.length&&estimate.rows.length>0&&<Typography.Text type="secondary">所选课程无需额外参数；真实课时将在选课结束、管理员确认后显示。</Typography.Text>}
    {!estimate.rows.length&&<Typography.Text type="secondary">选择课程后显示预估课时。</Typography.Text>}
  </div>;
}
