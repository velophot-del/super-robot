import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Form, Input, Result, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import { planningApi as api } from '../api/planning';

export default function TeacherProfilePage(){
  const {user}=useAuth(),navigate=useNavigate();
  const [record,setRecord]=useState<any>(),[courses,setCourses]=useState<string[]>([]),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [form]=Form.useForm();
  const teaching=can(user,'teaching');
  const load=useCallback(async()=>{
    if(!teaching)return;setLoading(true);setError('');
    try{const [data,options]=await Promise.all([api.selfProfile(),api.selfProfileCourses()]);setRecord(data);setCourses(options);form.setFieldsValue(data.profile);}
    catch(e){setError(e instanceof Error?e.message:'个人资料读取失败');}finally{setLoading(false);}
  },[teaching,form]);
  useEffect(()=>{void load();},[load]);
  const save=async(go:boolean)=>{
    let values;try{values=await form.validateFields();}catch{return;}
    setBusy(true);
    try{const data=await api.saveSelfProfile({...values,revision:record.revision});setRecord(data);form.setFieldsValue(data.profile);message.success('个人资料已保存，将用于课程匹配');if(go)navigate('/planning');}
    catch(e){message.error(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}
  };
  if(!teaching)return <Result status="403" title="账号没有教师资料维护职能"/>;
  return <Space orientation="vertical" size="large" style={{width:'100%',maxWidth:1000}}>
    <Typography.Title level={3}>我的个人资料</Typography.Title>
    <Alert showIcon type={record?.ready?'success':'warning'} title={record?.ready?'资料已完善，可以进入选课':'选课前请先完善专业方向、专业领域和擅长课程'}
      description="本人填写的专业资料将用于匹配，管理员可查看；教学团队、已核实曾授记录及课时上限由管理员维护。修改资料会使尚未审核的旧匹配结果需要重新计算。"/>
    {error&&<Alert type="error" showIcon title={error} action={<Button onClick={()=>void load()}>重新加载</Button>}/>}
    {loading?<Spin/>:record&&<>
      <Card title="基本信息"><Descriptions column={{xs:1,sm:2}} items={[
        {key:'name',label:'姓名',children:record.teacher.name},{key:'code',label:'工号',children:record.teacher.teacher_code},
        {key:'department',label:'所属部门',children:record.teacher.department||'未登记'},{key:'title',label:'职称',children:record.teacher.title||'未登记'},
      ]}/><Typography.Text type="secondary">基本身份信息如需更正，请联系管理员。</Typography.Text></Card>
      <Card title={<Space>专业资料<Tag color="blue">教师本人填写</Tag></Space>}>
        <Form form={form} layout="vertical" disabled={busy}>
          <Form.Item name="direction" label="专业方向" rules={[{required:true,whitespace:true,message:'请填写专业方向'}]} extra="填写主要专业方向，跨专业选课不会受此限制。"><Input maxLength={100} placeholder="例如：视觉传达设计、插画设计"/></Form.Item>
          <Form.Item name="tags" label="专业领域 / 擅长领域" rules={[{required:true,type:'array',min:1,message:'至少填写一个专业领域'}]} extra="输入后按回车确认，可填写多个领域。"><Select aria-label="专业领域" mode="tags" tokenSeparators={[',','，',';','；']} placeholder="例如：版式、品牌、信息可视化" options={['版式','品牌','插画','信息可视化','交互设计','设计研究'].map(t=>({value:t,label:t}))}/></Form.Item>
          <Form.Item name="skilled_courses" label="擅长课程" rules={[{required:true,type:'array',min:1,message:'至少选择或填写一门擅长课程'}]} extra="可从开放课程和生效培养方案中选择，也可输入课程名称后回车；不等于本次选课志愿。"><Select aria-label="擅长课程" mode="tags" tokenSeparators={[',','，',';','；']} showSearch placeholder="选择或输入擅长课程" options={courses.map(name=>({value:name,label:name}))}/></Form.Item>
          <Form.Item name="introduction" label="专业经历与个人说明"><Input.TextArea rows={4} maxLength={2000} showCount placeholder="可填写研究方向、教学经验或相关实践经历"/></Form.Item>
          <Space wrap><Form.Item name="contact_email" label="联系邮箱"><Input maxLength={200}/></Form.Item><Form.Item name="contact_phone" label="联系电话"><Input maxLength={50}/></Form.Item></Space>
          <Space wrap><Button loading={busy} onClick={()=>void save(false)}>保存资料</Button><Button type="primary" loading={busy} onClick={()=>void save(true)}>保存并进入选课</Button></Space>
        </Form>
      </Card>
    </>}
  </Space>;
}
