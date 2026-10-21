import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, InputNumber, Select, Space, Spin, Table, Tag, Typography, message } from 'antd';
import { planningApi } from '../api/planning';
import HelpTip from './HelpTip';

const kindNames:Record<string,string>={shared:'多人授课',design:'毕业设计',thesis:'毕业论文',ambiguous:'毕业设计（论文）',ordinary:'普通课程'};
const workloadHelp=<>
  <div>仅统计系统匹配后由管理员审核锁定（含已发布）的本人授课任务，选课阶段不显示。</div>
  <div>工作量 = 课时量 × 基数；按确认后的实际授课人数计算，25 人基数为 1，每增加 1 人基数增加 0.02，不足 25 人仍为 1。</div>
  <div>课时量按真实周内节次统计；无节次时按方案周课时与尾周课时还原，尾周较少时按真实课时计算。</div>
  <div>多人授课按各授课教师的本人上课周数比例分配；缺少任一位教师周数时该项待补充。</div>
  <div>毕业设计每生 12 课时，毕业论文每生 8 课时，按本人指导人数计算。</div>
</>;

export default function ConfirmedWorkloadPanel({plans,refreshKey=0}:{plans:any[];refreshKey?:number}){
  const [data,setData]=useState<any[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const [inputs,setInputs]=useState<Record<string,any>>({}),[saving,setSaving]=useState('');
  const ids=plans.filter(p=>p.state==='matched'||p.state==='published').map(p=>p.id).join(',');
  const load=useCallback(async()=>{
    const numbers=ids?ids.split(',').map(Number):[];
    if(!numbers.length){setData([]);setLoading(false);return;}
    setLoading(true);setError('');
    const results=await Promise.allSettled(numbers.map(id=>planningApi.myWorkload(id)));
    const loaded:any[]=[];let failed=0;
    results.forEach(result=>{if(result.status==='fulfilled'){if(result.value?.rows?.length)loaded.push(result.value);}else failed++;});
    setData(loaded);
    if(failed)setError(`${failed}个周期的确认工作量读取失败，请刷新重试。`);
    setLoading(false);
  },[ids]);
  useEffect(()=>{void load();},[load,refreshKey]);
  const change=(key:string,field:string,value:any)=>setInputs(old=>({...old,[key]:{...old[key],[field]:value}}));
  const save=async(planId:number,row:any,key:string)=>{
    setSaving(key);
    try{
      await planningApi.saveWorkloadEstimate(planId,row.task_id,{...(row.estimate||{}),...(inputs[key]||{}),revision:row.estimate?.revision??0});
      message.success('授课参数已保存，工作量已更新');
      await load();
    }catch(e){message.error(e instanceof Error?e.message:'保存失败，请刷新后重试');}
    finally{setSaving('');}
  };
  const rows=data.flatMap(workload=>workload.rows.map((row:any)=>({...row,key:`${workload.plan_id}-${row.task_id}`,plan:workload})));
  if(loading&&!rows.length)return <Card title="已确认工作量"><Spin/></Card>;
  return <Card title="已确认真实工作量" extra={<Space wrap><HelpTip title={workloadHelp}/><Button size="small" onClick={()=>void load()} disabled={loading}>刷新</Button></Space>}>
    {error&&<Alert type="error" showIcon title={error} style={{marginBottom:12}}/>}
    {!rows.length?<Empty description="管理员确认授课安排后，将在此生成准确工作量"/>:
      <Space orientation="vertical" style={{width:'100%'}} size="middle">{data.map(workload=><Card key={workload.plan_id} size="small"
        title={<Space wrap><Typography.Text strong>{workload.plan_name}</Typography.Text><Tag>{workload.plan_state==='published'?'已发布':'审核已确认'}</Tag></Space>}
        extra={<Space wrap><Tag color="purple">合计 {Number(workload.total||0).toFixed(2)} 课时</Tag>{workload.pending>0&&<Tag color="orange">{workload.pending}项待补充参数</Tag>}</Space>}>
        <Table rowKey="key" dataSource={workload.rows} pagination={false} size="small" scroll={{x:1000}} columns={[
          {title:'课程',render:(_,row:any)=><Space orientation="vertical" size={0}><Typography.Text strong>{row.name}</Typography.Text><Typography.Text type="secondary">{row.group} · {kindNames[row.kind]||row.kind}</Typography.Text></Space>},
          {title:'人数 / 基数',render:(_,row:any)=>`${row.student_count}人 / ${row.base}`},
          {title:'课时量',render:(_,row:any)=>row.kind==='design'||row.kind==='thesis'?(row.guidance_students!=null?`${row.guidance_students}生`:'—'):(row.course_hours??'—')},
          {title:'分配',render:(_,row:any)=>row.kind==='design'||row.kind==='thesis'?'按指导人数':(row.allocation||'—')},
          {title:'工作量',render:(_,row:any)=>row.status==='confirmed'?<Typography.Text strong>{Number(row.workload).toFixed(2)} 课时</Typography.Text>:<Tag color="orange">待确认</Tag>},
          {title:'计算 / 说明',render:(_,row:any)=>row.status==='confirmed'?<Typography.Text type="secondary">{row.formula}</Typography.Text>:<Space orientation="vertical" size={4}>
            <Typography.Text type="warning">{row.note}</Typography.Text>
            {row.plan.plan_state!=='published'&&<Space wrap>
              {row.kind==='shared'?<InputNumber aria-label={`确认后授课周数 ${row.key}`} min={0} max={100} precision={0} placeholder="本人授课周数" value={inputs[row.key]?.weeks??row.estimate?.weeks??undefined} onChange={value=>change(row.key,'weeks',value)}/>
                :<>
                  {row.kind==='ambiguous'&&<Select aria-label={`确认后指导类型 ${row.key}`} style={{width:120}} placeholder="指导类型" value={inputs[row.key]?.guidance_kind??row.estimate?.guidance_kind??undefined} options={[{value:'design',label:'毕业设计'},{value:'thesis',label:'毕业论文'}]} onChange={value=>change(row.key,'guidance_kind',value)}/>}
                  <InputNumber aria-label={`确认后指导人数 ${row.key}`} min={0} max={10000} precision={0} placeholder="本人指导人数" value={inputs[row.key]?.guidance_students??row.estimate?.guidance_students??undefined} onChange={value=>change(row.key,'guidance_students',value)}/>
                </>}
              <Button size="small" loading={saving===row.key} onClick={()=>void save(row.plan.plan_id,row,row.key)}>保存参数</Button>
            </Space>}
          </Space>},
        ]}/>
      </Card>)}</Space>}
  </Card>;
}
