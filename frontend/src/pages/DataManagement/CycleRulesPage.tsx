import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, DatePicker, Descriptions, InputNumber, Modal, Space, Table, Tag, Typography, message } from 'antd';
import { Link } from 'react-router-dom';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { planningApi } from '../../api/planning';
import { gradeLabel } from '../../lib/adminStageGrid';

const states:Record<string,string>={draft:'草稿',open:'填报中',matched:'匹配完成',published:'已发布',closed:'已关闭'};
export default function CycleRulesPage(){
  const [plans,setPlans]=useState<any[]>([]),[loading,setLoading]=useState(false);
  const [rules,setRules]=useState<any[]>([]),[editing,setEditing]=useState<any>(),[saving,setSaving]=useState(false);
  const [weeks,setWeeks]=useState(20),[startDate,setStartDate]=useState<Dayjs|null>(null),[examWeeks,setExamWeeks]=useState<number[]>([]);
  const load=useCallback(async()=>{setLoading(true);try{const [nextPlans,nextRules]=await Promise.all([planningApi.plans(),planningApi.calendarRules()]);setPlans(nextPlans);setRules(nextRules);}catch(e){message.error(e instanceof Error?e.message:'周期或规则加载失败');}finally{setLoading(false);}},[]);
  useEffect(()=>{void load();},[load]);
  const editRule=(row:any)=>{setEditing(row);setWeeks(row.weeks||20);setStartDate(row.start_date?dayjs(row.start_date):null);setExamWeeks(row.exam_weeks||[]);};
  const toggleExam=(week:number)=>setExamWeeks(current=>current.includes(week)?current.filter(value=>value!==week):[...current,week].sort((a,b)=>a-b));
  const saveRule=async()=>{
    if(!editing||!startDate){message.error('请选择课程开始日期');return;}
    if(startDate.day()!==1){message.error('课程开始日期必须为周一');return;}
    setSaving(true);
    try{await planningApi.saveCalendarRule(editing.cohort,{weeks,start_date:startDate.format('YYYY-MM-DD'),exam_weeks:examWeeks});message.success(`${gradeLabel(editing.cohort)||`${editing.cohort}级`}规则已保存，适用于该年级全部专业班级`);setEditing(undefined);await load();}
    catch(e){message.error(e instanceof Error?e.message:'年级规则保存失败');}
    finally{setSaving(false);}
  };
  return <Space direction="vertical" size={16} style={{width:'100%'}}>
    <div><Typography.Title level={3}>开课周期与规则</Typography.Title><Typography.Text type="secondary">在此按年级统一设置课程开始日期、授课周数和考试周；规则对该年级所有专业班级生效。</Typography.Text></div>
    <Alert showIcon type="info" title="年级统一日历规则" description="修改后的规则用于排课、考试周冲突校验和课表日期。若新规则与已有课程周段冲突，系统会拒绝保存并列出冲突课程；已发布课表保留发布时的规则快照。"/>
    <Card title="年级开课规则" extra={<Button icon={<ReloadOutlined/>} onClick={()=>void load()} loading={loading}>刷新</Button>}>
      <Table rowKey="cohort" loading={loading} dataSource={rules} pagination={{pageSize:10}} locale={{emptyText:'暂无班级年级数据'}} columns={[
        {title:'年级',dataIndex:'cohort',render:(v:string)=>gradeLabel(v)||`${v}级`},
        {title:'课程开始日期',dataIndex:'start_date',render:(v:string)=>v||'待设置'},
        {title:'授课周期',dataIndex:'weeks',render:(v:number)=>`${v}周`},
        {title:'考试周',dataIndex:'exam_weeks',render:(v:number[])=>v?.length?v.map(n=>`第${n}周`).join('、'):'未设考试周'},
        {title:'来源',dataIndex:'source',render:(_:unknown,row:any)=>row.configured?<Tag color="green">管理员设置</Tag>:<Tag>{row.source||'待设置'}</Tag>},
        {title:'操作',render:(_:unknown,row:any)=><Button type="link" onClick={()=>editRule(row)}>{row.configured?'编辑':'设置'}</Button>},
      ]}/>
    </Card>
    <Card title="当前排课规则">
      <Descriptions bordered size="small" column={{xs:1,md:2}} items={[
        {key:'length',label:'授课周期',children:'按年级设置，最多20周；排课周期中的周次网格仍按周期长度展示。'},
        {key:'exam',label:'考试周',children:'按年级设置，对该年级所有专业和班级统一生效。'},
        {key:'start',label:'课程开始日期',children:'按年级设置，须为周一；甘特图日期和冲突日期计算以此为准。'},
        {key:'group',label:'教学组周上限',children:'每个教学组每周最多2门专业课、每天最多1门。'},
        {key:'release',label:'发布校验',children:'正式发布前校验课程周段、考试周、学时、教师、教室及冲突。'},
      ]}/>
    </Card>
    <Card title={`已有排课周期（${plans.length}）`} extra={<Button icon={<ReloadOutlined/>} onClick={()=>void load()} loading={loading}>刷新</Button>}>
      <Table rowKey="id" loading={loading} dataSource={plans} pagination={{pageSize:10}} locale={{emptyText:'暂无排课周期'}} columns={[
        {title:'周期',dataIndex:'name'},
        {title:'学年 / 学期',render:(_:unknown,p:any)=>`${p.academic_year||'—'} · 第${p.academic_term||'—'}学期`},
        {title:'范围',render:(_:unknown,p:any)=>p.global_cycle?'全学院':`${p.major||'未设专业'} · ${gradeLabel(p.cohort)||'未设届次'}`},
        {title:'周数',dataIndex:'weeks',width:80,render:(v:number)=>`${v}周`},
        {title:'状态',dataIndex:'state',width:100,render:(v:string)=><Tag color={v==='published'?'green':v==='open'?'blue':'default'}>{states[v]||v}</Tag>},
        {title:'操作',width:150,render:()=> <Link to="/planning"><Button type="link">在周期计划中管理</Button></Link>},
      ]}/>
    </Card>
    <Modal title={`${editing?(gradeLabel(editing.cohort)||`${editing.cohort}级`):''}开课规则`} open={!!editing} onCancel={()=>setEditing(undefined)} onOk={()=>void saveRule()} confirmLoading={saving} okText="保存规则" cancelText="取消" width={680}>
      {editing&&<Space direction="vertical" size="middle" style={{width:'100%'}}>
        <Typography.Text>此规则对{gradeLabel(editing.cohort)||`${editing.cohort}级`}所有专业班级统一生效。</Typography.Text>
        <Space wrap><Typography.Text strong>课程开始日期</Typography.Text><DatePicker aria-label="课程开始日期" value={startDate} onChange={setStartDate} format="YYYY-MM-DD"/><Typography.Text type="secondary">须选择周一</Typography.Text></Space>
        <Space wrap><Typography.Text strong>授课周数</Typography.Text><InputNumber min={1} max={20} value={weeks} onChange={value=>{const next=Number(value)||1;setWeeks(next);setExamWeeks(current=>current.filter(week=>week<=next));}}/><Typography.Text type="secondary">周（最多20周）</Typography.Text></Space>
        <div><Typography.Text strong>考试周</Typography.Text><div style={{display:'flex',flexWrap:'wrap',gap:6,marginTop:8}}>{Array.from({length:weeks},(_,index)=>index+1).map(week=><Button key={week} size="small" type={examWeeks.includes(week)?'primary':'default'} aria-pressed={examWeeks.includes(week)} onClick={()=>toggleExam(week)}>第{week}周</Button>)}</div><Typography.Text type="secondary">可多选；不设考试周时请保持未选中。</Typography.Text></div>
      </Space>}
    </Modal>
  </Space>;
}
