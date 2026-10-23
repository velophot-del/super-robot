import { useState } from 'react';
import { Alert, Button, Empty, Modal, Select, Space, message } from 'antd';
import { planningApi } from '../api/planning';
import { gradeLabel } from '../lib/adminStageGrid';

type ExportOption = {major:string;start_date:string;weeks:number;cohort:string;term:string};

export default function ProfessionalExport(){
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[options,setOptions]=useState<ExportOption[]>([]);
  const [major,setMajor]=useState<string>(),[term,setTerm]=useState<string>(),[cohort,setCohort]=useState<string>();
  const termKey=(o:ExportOption)=>`${o.start_date}|${o.weeks}`;
  const majors=[...new Set(options.map(o=>o.major))];
  const terms=[...new Map(options.filter(o=>o.major===major).map(o=>[termKey(o),o])).values()];
  const cohorts=[...new Set(options.filter(o=>o.major===major&&termKey(o)===term).map(o=>o.cohort))];
  const show=async()=>{
    setOpen(true);setBusy(true);
    try{const data=await planningApi.exportOptions();setOptions(data);setMajor(data[0]?.major);setTerm(data[0]?termKey(data[0]):undefined);setCohort(undefined);}
    catch(e){setOptions([]);message.error(e instanceof Error?e.message:'读取可导出课表失败');}finally{setBusy(false);}
  };
  const download=async()=>{
    if(!major||!term)return;setBusy(true);
    try{
      const [start_date,weeks]=term.split('|');
      const blob=await planningApi.exportWord({major,start_date,weeks:Number(weeks),...(cohort!==undefined?{cohort}:{})});
      const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;
      a.download=`${major}_${start_date}_${cohort||'全部年级'}_专业课总表.docx`;
      document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      message.success('已导出Word专业课总表');setOpen(false);
    }catch(e){message.error(e instanceof Error?e.message:'导出失败');}finally{setBusy(false);}
  };
  return <><Button onClick={()=>void show()}>按专业导出Word课表</Button>
    <Modal title="按专业导出学院格式课表" open={open} onCancel={()=>setOpen(false)} onOk={()=>void download()}
      okText="下载Word课表" confirmLoading={busy} okButtonProps={{disabled:!major||!term||!options.length}}>
      <Space orientation="vertical" style={{width:'100%'}} size="middle">
        <Alert type="info" showIcon title="仅导出已发布快照，按年级分页" description="保留学院横向周次表样式；同周两门上下排列。教师及审核人仅能导出本人或授权范围内的课程。"/>
        {!options.length&&!busy?<Empty description="暂无有权导出的已发布课表，请先完成审核发布并设置专业和年级"/>:<>
          <label>专业<Select aria-label="导出专业" style={{width:'100%'}} value={major} options={majors.map(m=>({value:m,label:m}))}
            onChange={value=>{setMajor(value);const first=options.find(o=>o.major===value);setTerm(first?termKey(first):undefined);setCohort(undefined);}}/></label>
          <label>学年学期与周期<Select aria-label="导出学年学期" style={{width:'100%'}} value={term}
            options={terms.map(o=>({value:termKey(o),label:`${o.term} · ${o.start_date}起 · ${o.weeks}周`}))}
            onChange={value=>{setTerm(value);setCohort(undefined);}}/></label>
          <label>年级<Select aria-label="导出年级" style={{width:'100%'}} value={cohort} placeholder="全部年级（分别分页）" allowClear
            options={cohorts.map(c=>({value:c,label:gradeLabel(c)||'未设置年级'}))} onChange={setCohort}/></label>
        </>}
      </Space>
    </Modal></>;
}
