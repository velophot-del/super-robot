import { useState } from 'react';
import { Alert, Button, DatePicker, Input, InputNumber, Modal, Radio, Select, Space, message } from 'antd';
import { planningApi } from '../api/planning';
import dayjs from 'dayjs';
import {suggestedMonday} from '../lib/academicCalendar';
import { gradeLabel } from '../lib/adminStageGrid';

type ExportOption = {major:string;start_date:string;weeks:number;cohort:string;term:string;
  plan_id:number;plan_name:string;state:string;source:string};
const stateNames:Record<string,string>={draft:'草稿',open:'开放填报',matched:'匹配中',published:'已发布'};
const BLANK_MAJOR='未设置专业（空白稿）';
const majorKey=(o:ExportOption)=>o.major||BLANK_MAJOR;

export default function ProfessionalExport(){
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[options,setOptions]=useState<ExportOption[]>([]);
  const [blank,setBlank]=useState(false),[blankMajor,setBlankMajor]=useState('');
  const [blankDate,setBlankDate]=useState(suggestedMonday(dayjs().format('YYYY-MM-DD'))||dayjs().format('YYYY-MM-DD')),[blankWeeks,setBlankWeeks]=useState(20);
  const [major,setMajor]=useState<string>(),[term,setTerm]=useState<string>(),[cohort,setCohort]=useState<string>();
  const termKey=(o:ExportOption)=>`${o.plan_id}|${o.start_date}|${o.weeks}`;
  const majors=[...new Set(options.map(majorKey))];
  const terms=[...new Map(options.filter(o=>majorKey(o)===major).map(o=>[termKey(o),o])).values()];
  const cohorts=[...new Set(options.filter(o=>majorKey(o)===major&&termKey(o)===term).map(o=>o.cohort))];
  const show=async()=>{
    setOpen(true);setBusy(true);
    try{const data=await planningApi.exportOptions();setOptions(data);setMajor(data[0]?majorKey(data[0]):undefined);setTerm(data[0]?termKey(data[0]):undefined);setCohort(undefined);setBlank(!data.length);setBlankMajor(data[0]?.major||'');if(data[0])setBlankDate(data[0].start_date);}
    catch(e){setOptions([]);setBlank(true);message.error(e instanceof Error?e.message:'读取可导出课表失败');}finally{setBusy(false);}
  };
  const download=async()=>{
    if(!blank&&(major===undefined||!term))return;if(blank&&!blankDate)return;setBusy(true);
    try{
      const [planId,start_date,weeks]=blank?['',blankDate,String(blankWeeks)]:term!.split('|');
      const exportMajor=blank?blankMajor.trim():(major===BLANK_MAJOR?'':major);
      const blob=await planningApi.exportWord({...(blank?{blank:true}:{plan_id:Number(planId)}),start_date,weeks:Number(weeks),
        ...(exportMajor?{major:exportMajor}:{}),...(cohort!==undefined?{cohort}:{})});
      const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;
      a.download=`${exportMajor||'未设置专业'}_${start_date}_${cohort||'全部年级'}_专业课总表.docx`;
      document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      message.success('已导出Word专业课总表');setOpen(false);
    }catch(e){message.error(e instanceof Error?e.message:'导出失败');}finally{setBusy(false);}
  };
  return <><Button onClick={()=>void show()}>按专业导出Word课表</Button>
    <Modal title="按专业导出学院格式课表" open={open} onCancel={()=>setOpen(false)} onOk={()=>void download()}
      okText="下载Word课表" confirmLoading={busy} okButtonProps={{disabled:busy||(blank?!blankDate:major===undefined||!term||!options.length)}}>
      <Space orientation="vertical" style={{width:'100%'}} size="middle">
        <Alert type="info" showIcon title="随时导出：已发布快照、过程稿、空白稿" description="已发布周期优先使用不可变快照；草稿/开放/匹配中的周期按当前任务生成；没有课程任务时输出空白表模板。保留学院横向周次表样式，按年级分页。"/>
        <Radio.Group value={blank} onChange={event=>setBlank(event.target.value)} options={[{value:false,label:'当前课表 / 过程稿',disabled:!options.length},{value:true,label:'空白模板'}]}/>
        {blank?<><label>专业<Input aria-label="空白课表专业" placeholder="可留空" value={blankMajor} onChange={event=>setBlankMajor(event.target.value)}/></label>
          <label>第1教学周周一<DatePicker aria-label="空白课表起始日期" value={blankDate?dayjs(blankDate):null} onChange={value=>setBlankDate(value?.format('YYYY-MM-DD')||'')} style={{width:'100%'}} disabledDate={value=>value.day()!==1}/></label>
          <label>学期周数<InputNumber aria-label="空白课表周数" min={18} max={20} value={blankWeeks} onChange={value=>setBlankWeeks(value||20)} style={{width:'100%'}}/></label>
          <label>年级<Input aria-label="空白课表年级" placeholder="可留空，例如2026" value={cohort||''} onChange={event=>setCohort(event.target.value||undefined)}/></label></>:<>
          <label>专业<Select aria-label="导出专业" style={{width:'100%'}} value={major} options={majors.map(m=>({value:m,label:m}))}
            onChange={value=>{setMajor(value);const first=options.find(o=>majorKey(o)===value);setTerm(first?termKey(first):undefined);setCohort(undefined);}}/></label>
          <label>学年学期与周期<Select aria-label="导出学年学期" style={{width:'100%'}} value={term}
            options={terms.map(o=>({value:termKey(o),label:`${o.term} · ${o.plan_name||`周期${o.plan_id}`} · ${stateNames[o.state]||o.state} · ${o.start_date}起 · ${o.weeks}周`}))}
            onChange={value=>{setTerm(value);setCohort(undefined);}}/></label>
          <label>年级<Select aria-label="导出年级" style={{width:'100%'}} value={cohort} placeholder="全部年级（分别分页）" allowClear
            options={cohorts.map(c=>({value:c,label:gradeLabel(c)||'未设置年级'}))} onChange={setCohort}/></label>
        </>}
      </Space>
    </Modal></>;
}
