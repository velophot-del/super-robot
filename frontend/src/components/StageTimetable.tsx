import { useState } from 'react';
import { Button, Card, Select, Space, Tag, Typography } from 'antd';
import { stageCell } from '../lib/stageGrid';

export default function StageTimetable({tasks,weeks,selected,onTask,disabled}:{tasks:any[];weeks:number;selected:number[];onTask:(task:any)=>void;disabled:boolean}){
  const [group,setGroup]=useState(''),[week,setWeek]=useState(1);
  const groups=[...new Set(tasks.map(t=>t.group))];
  const current=groups.includes(group)?group:groups[0];
  const filtered=tasks.filter(t=>t.group===current);
  return <Card title="阶段式课表 · 点击课程查看或预选" style={{marginBottom:20}}>
    <Space wrap style={{marginBottom:14}}><Select aria-label="课表教学组" style={{minWidth:180}} value={current} onChange={setGroup} options={groups.map(g=>({value:g,label:g}))}/>
      <Select aria-label="课表周次" value={week} onChange={setWeek} options={Array.from({length:weeks},(_,i)=>({value:i+1,label:`第${i+1}周`}))}/>
      <Tag color="purple">实色：实际授课</Tag><Tag>斜纹：该课程保留，不计授课学时</Tag><Tag>空白：未安排</Tag></Space>
    <div style={{overflowX:'auto'}}><table style={{width:'100%',minWidth:640,borderCollapse:'collapse',tableLayout:'fixed'}}>
      <thead><tr><th style={{width:60}}>节次</th>{['周一','周二','周三','周四','周五','周六','周日'].map(d=><th key={d} style={{padding:10}}>{d}</th>)}</tr></thead>
      <tbody>{Array.from({length:8},(_,i)=>i+1).map(period=><tr key={period}><th style={{border:'1px solid #eee'}}>第{period}节</th>{Array.from({length:7},(_,i)=>i+1).map(day=>{
        const cell=stageCell(filtered,week,day,period),task=cell.task;
        return <td key={day} style={{height:56,border:'1px solid #e5e7eb',padding:3,background:cell.state==='reserved'?'repeating-linear-gradient(135deg,#f3f0ff,#f3f0ff 5px,#e2dcf9 5px,#e2dcf9 8px)':'white'}}>
          {cell.state==='teaching'&&<Button type={selected.includes(task!.id)?'primary':'default'} block style={{height:48,whiteSpace:'normal',fontSize:12}} disabled={disabled} onClick={()=>onTask(task)}>{task!.name}{selected.includes(task!.id)?' ✓':''}</Button>}
          {cell.state==='reserved'&&<span style={{fontSize:11,color:'#81739d'}}>课程保留</span>}
        </td>;
      })}</tr>)}</tbody>
    </table></div>
    <Typography.Paragraph type="secondary" style={{marginTop:12,marginBottom:0}}>同教学组同周最多2门，同日只能1门。预选不会改变课程的周段和时段。</Typography.Paragraph>
  </Card>;
}
