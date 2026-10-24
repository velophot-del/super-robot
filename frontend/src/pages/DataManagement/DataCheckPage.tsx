import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Row, Space, Spin, Statistic, Table, Tag, Typography, message } from 'antd';
import { Link } from 'react-router-dom';
import { classApi, classroomApi, courseApi, teacherApi } from '../../api/client';
import { planningApi } from '../../api/planning';

type Issue={key:string;category:string;level:'需处理'|'提示';count:number;examples:string;path:string;destination:string};
async function allRows(api:{list:(params?:any)=>Promise<any[]>},extra:Record<string,unknown>={}){
  const rows:any[]=[];let skip=0;
  while(skip<10000){const page=await api.list({skip,limit:500,...extra});if(!Array.isArray(page))throw new Error('数据接口返回格式异常');rows.push(...page);if(page.length<500)break;skip+=page.length;}
  return rows;
}

export default function DataCheckPage(){
  const [loading,setLoading]=useState(false),[error,setError]=useState('');
  const [issues,setIssues]=useState<Issue[]>([]),[counts,setCounts]=useState({courses:0,teachers:0,classrooms:0,classes:0});
  const run=useCallback(async()=>{
    setLoading(true);setError('');
    try{
      const [courses,teachers,classrooms,classes,units,programs,directions]=await Promise.all([
        allRows(courseApi,{include_inactive:true,include_public:true}),allRows(teacherApi),allRows(classroomApi),allRows(classApi),planningApi.offeringUnits(),planningApi.programs(),planningApi.directions(),
      ]);
      setCounts({courses:courses.length,teachers:teachers.length,classrooms:classrooms.length,classes:classes.length});
      const found:Issue[]=[];
      const add=(key:string,category:string,level:Issue['level'],items:string[],path:string,destination:string)=>{if(items.length)found.push({key,category,level,count:items.length,examples:items.slice(0,4).join('、'),path,destination});};
      const codeGroups=new Map<string,any[]>();for(const c of courses){const code=String(c.course_code||'').trim();if(code)codeGroups.set(code,[...(codeGroups.get(code)||[]),c]);}
      add('duplicate-codes','课程编码重复','需处理',[...codeGroups].filter(([,group])=>group.length>1).map(([code])=>code),'/data/courses','课程管理');
      add('course-semester','课程缺少有效开课学期','需处理',courses.filter(c=>!Number.isInteger(c.semester)||c.semester<1||c.semester>12).map(c=>c.name),'/data/courses','课程管理');
      add('course-hours','课程缺少有效计划总学时','需处理',courses.filter(c=>!Number.isFinite(Number(c.total_hours))||Number(c.total_hours)<=0).map(c=>c.name),'/data/courses','课程管理');
      add('course-weeks','课程未设置授课周数','提示',courses.filter(c=>c.is_active!==false&&(c.teaching_weeks==null||c.teaching_weeks<1||c.teaching_weeks>20)).map(c=>c.name),'/data/courses','课程管理');
      const unitIds=new Set(units.map(u=>u.id));
      add('teacher-department','教师未关联管理员教研室','提示',teachers.filter(t=>!t.offering_unit_id||!unitIds.has(t.offering_unit_id)).map(t=>`${t.name}（${t.department||'未设置'}）`),'/data/teachers','教师管理');
      add('teacher-unit-ref','教师关联的教研室不存在','需处理',teachers.filter(t=>t.offering_unit_id&&!unitIds.has(t.offering_unit_id)).map(t=>t.name),'/data/teachers','教师管理');
      add('course-unit','活动课程未关联开课教研室','提示',courses.filter(c=>c.is_active!==false&&!c.offering_unit_id).map(c=>c.name),'/data/courses','课程管理');
      add('course-unit-ref','课程关联的开课教研室不存在','需处理',courses.filter(c=>c.offering_unit_id&&!unitIds.has(c.offering_unit_id)).map(c=>c.name),'/data/courses','课程管理');
      const programNames=new Set(programs.map(p=>p.name));
      const programIds=new Set(programs.map(p=>p.id));
      add('course-program-link','活动课程未关联管理员专业','提示',courses.filter(c=>c.is_active!==false&&c.department&&(!c.program_id||!programIds.has(c.program_id))).map(c=>`${c.name}（${c.department}）`),'/data/courses','课程管理');
      add('course-program-ref','课程关联的标准专业不存在','需处理',courses.filter(c=>c.program_id&&!programIds.has(c.program_id)).map(c=>c.name),'/data/courses','课程管理');
      add('course-program','课程适用专业未匹配标准专业目录','提示',courses.filter(c=>c.department&&String(c.department).split(/[,，、]/).map((x:string)=>x.trim()).some((name:string)=>name&&!programNames.has(name))).map(c=>`${c.name}（${c.department}）`),'/data/programs-grades','专业目录');
      add('class-grade','班级届次格式异常','需处理',classes.filter(c=>!/^\d{4}(届|级)?$/.test(String(c.grade||''))).map(c=>c.name),'/data/classes','班级管理');
      add('class-program','班级未关联标准专业','提示',classes.filter(c=>c.is_active!==false&&!c.program_id).map(c=>c.name),'/data/programs-grades','专业 / 年级管理');
      add('class-program-ref','班级关联的标准专业不存在','需处理',classes.filter(c=>c.program_id&&!programIds.has(c.program_id)).map(c=>c.name),'/data/programs-grades','专业 / 年级管理');
      const programMap=new Map(programs.map(p=>[p.id,p]));
      add('class-program-label','班级专业名称与管理员目录不一致','需处理',classes.filter(c=>c.program_id&&programMap.has(c.program_id)&&c.department!==programMap.get(c.program_id)?.name).map(c=>c.name),'/data/classes','班级管理');
      const directionIds=new Set(directions.map(d=>d.id));
      add('course-direction','课程方向关联无效','需处理',courses.filter(c=>c.direction_id&&!directionIds.has(c.direction_id)).map(c=>c.name),'/data/courses','课程管理');
      const directionMap=new Map(directions.map(d=>[d.id,d]));
      add('course-direction-program','课程专业与方向不一致','需处理',courses.filter(c=>c.direction_id&&directionMap.has(c.direction_id)&&c.program_id!==directionMap.get(c.direction_id)?.program_id).map(c=>c.name),'/data/courses','课程管理');
      add('direction-program','专业方向关联的专业不存在','需处理',directions.filter(d=>!programIds.has(d.program_id)).map(d=>d.name),'/data/programs-grades?tab=directions','专业 / 教研室管理');
      add('direction-unit-ref','专业方向关联的教研室不存在','需处理',directions.filter(d=>d.offering_unit_id&&!unitIds.has(d.offering_unit_id)).map(d=>d.name),'/data/programs-grades?tab=directions','专业 / 教研室管理');
      add('direction-unit','专业方向未关联开课教研室','提示',directions.filter(d=>!d.offering_unit_id).map(d=>`${d.program_name}—${d.name}`),'/data/programs-grades?tab=directions','专业 / 教研室管理');
      add('room-capacity','教室容量无效','需处理',classrooms.filter(r=>!Number.isFinite(Number(r.capacity))||Number(r.capacity)<1).map(r=>r.name),'/data/classrooms','教室管理');
      setIssues(found);
    }catch(e){const text=e instanceof Error?e.message:'数据检查失败';setError(text);message.error(text);}finally{setLoading(false);}
  },[]);
  useEffect(()=>{void run();},[run]);
  return <Space direction="vertical" size={16} style={{width:'100%'}}>
    <div><Typography.Title level={3}>数据检查</Typography.Title><Typography.Text type="secondary">只读检查课程、教师、教室、班级与目录之间的关键字段和关联；检查不会自动修改数据。</Typography.Text></div>
    {error&&<Alert type="error" showIcon title="检查未完成" description={error} action={<Button onClick={()=>void run()}>重试</Button>}/>}
    <Row gutter={[12,12]}>{[['课程',counts.courses],['教师',counts.teachers],['教室',counts.classrooms],['班级',counts.classes]].map(([label,value])=><Col xs={12} md={6} key={String(label)}><Card><Statistic title={`已检查${label}`} value={value}/></Card></Col>)}</Row>
    <Card title="检查结果" extra={<Button onClick={()=>void run()} loading={loading}>重新检查</Button>}>
      {loading&&!issues.length?<div style={{textAlign:'center',padding:32}}><Spin/></div>:<Table rowKey="key" dataSource={issues} pagination={false} locale={{emptyText:'未发现需要处理的问题'}} columns={[
        {title:'检查项',dataIndex:'category'},
        {title:'等级',dataIndex:'level',width:100,render:(v:string)=><Tag color={v==='需处理'?'red':'orange'}>{v}</Tag>},
        {title:'记录数',dataIndex:'count',width:90},
        {title:'示例',dataIndex:'examples',ellipsis:true},
        {title:'处理入口',width:180,render:(_:unknown,row:Issue)=><Link to={row.path}><Button type="link">打开{row.destination}</Button></Link>},
      ]}/>}
      {!!issues.length&&<Typography.Text type="secondary">共发现 {issues.reduce((n,x)=>n+x.count,0)} 条待核对记录。示例最多展示4条；请进入对应页面查看完整数据。</Typography.Text>}
    </Card>
  </Space>;
}
