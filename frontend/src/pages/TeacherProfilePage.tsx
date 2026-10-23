import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Form, Input, Result, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import { planningApi as api } from '../api/planning';

const TEACHER_DIRECTIONS = ['视觉传达设计','包装设计','智能交互设计','数字艺术','时尚传播'];

export default function TeacherProfilePage(){
  const {user,refreshUser,changePassword}=useAuth(),navigate=useNavigate();
  const [record,setRecord]=useState<any>(),[courses,setCourses]=useState<string[]>([]),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [courseGroups,setCourseGroups]=useState<{id:number;name:string;course_code:string;department?:string}[]>([]);
  const [form]=Form.useForm();
  const [passwordForm]=Form.useForm();
  const [passwordBusy,setPasswordBusy]=useState(false);
  const teaching=can(user,'teaching');
  const load=useCallback(async()=>{
    if(!teaching)return;setLoading(true);setError('');
    try{const [data,options,groups]=await Promise.all([api.selfProfile(),api.selfProfileCourses(),api.selfProfileCourseGroups()]);setRecord(data);setCourses(options);setCourseGroups(groups);form.setFieldsValue(data.profile);}
    catch(e){setError(e instanceof Error?e.message:'个人资料读取失败');}finally{setLoading(false);}
  },[teaching,form]);
  useEffect(()=>{void load();},[load]);
  const save=async(go:boolean)=>{
    let values;try{values=await form.validateFields();}catch{return;}
    setBusy(true);
    try{const data=await api.saveSelfProfile({...values,revision:record.revision});setRecord(data);form.setFieldsValue(data.profile);message.success('个人资料已保存，将用于课程匹配');const current=await refreshUser();if(go){if(current.password_change_required||current.profile_required)message.warning('请先完成密码修改和个人资料');else navigate('/planning');}}
    catch(e){message.error(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}
  };
  if(!teaching)return <Result status="403" title="账号没有教师资料维护职能"/>;
  return <Space orientation="vertical" size="large" style={{width:'100%',maxWidth:1000}}>
    <Typography.Title level={3}>我的个人资料</Typography.Title>
    {!user?.is_demo&&<Card title={user?.password_change_required?'首次登录：必须修改初始密码':'修改登录密码'}>
      {user?.password_change_required&&<Alert type="warning" showIcon title="修改初始密码并完善专业资料后，才能使用其他功能" style={{marginBottom:16}}/>}
      <Form form={passwordForm} layout="vertical" onFinish={async values=>{
        setPasswordBusy(true);try{await changePassword({current_password:values.current_password,new_password:values.new_password});passwordForm.resetFields();message.success('密码已修改；请确认个人资料已完善');}catch(e){message.error(e instanceof Error?e.message:'修改失败');}finally{setPasswordBusy(false);}
      }}>
        <Form.Item name="current_password" label="当前密码" rules={[{required:true}]}><Input.Password autoComplete="current-password"/></Form.Item>
        <Form.Item name="new_password" label="新密码" rules={[{required:true},{min:6,max:128,message:'密码长度为6—128位'}]}><Input.Password autoComplete="new-password"/></Form.Item>
        <Form.Item name="confirm_password" label="确认新密码" dependencies={['new_password']} rules={[{required:true},({getFieldValue})=>({validator:(_,v)=>v===getFieldValue('new_password')?Promise.resolve():Promise.reject(new Error('两次密码不一致'))})]}><Input.Password autoComplete="new-password"/></Form.Item>
        <Button type="primary" htmlType="submit" loading={passwordBusy}>修改密码</Button>
      </Form>
    </Card>}
    <Alert showIcon type={record?.ready?'success':'warning'} title={record?.ready?'资料已完善，可以进入选课':'选课前请先完善专业方向、专业领域和擅长课程'}
      description="本人填写的专业资料将用于匹配，管理员可查看；参与课程组由本人申报，已核实教学团队、曾授记录及课时上限由管理员维护。修改资料会使尚未审核的旧匹配结果需要重新计算。"/>
    {error&&<Alert type="error" showIcon title={error} action={<Button onClick={()=>void load()}>重新加载</Button>}/>}
    {loading?<Spin/>:record&&<>
      <Card title="基本信息"><Descriptions column={{xs:1,sm:2}} items={[
        {key:'name',label:'姓名',children:record.teacher.name},{key:'code',label:'工号',children:record.teacher.teacher_code},
        {key:'department',label:'所属部门',children:record.teacher.department||'未登记'},{key:'title',label:'职称',children:record.teacher.title||'未登记'},
      ]}/><Typography.Text type="secondary">基本身份信息如需更正，请联系管理员。</Typography.Text></Card>
      <Card title={<Space>专业资料<Tag color="blue">教师本人填写</Tag></Space>}>
        <Form form={form} layout="vertical" disabled={busy}>
          <Form.Item name="direction" label="专业方向" rules={[{required:true,whitespace:true,message:'请选择专业方向'}]} extra="请选择最符合本人教学与研究方向的一项；跨专业选课不会受此限制。">
            <Select aria-label="专业方向" placeholder="请选择专业方向" options={TEACHER_DIRECTIONS.map(direction=>({value:direction,label:direction}))}/>
          </Form.Item>
          <Form.Item name="tags" label="专业领域 / 擅长领域" rules={[{required:true,type:'array',min:1,message:'至少填写一个专业领域'}]} extra="输入后按回车确认，可填写多个领域。"><Select aria-label="专业领域" mode="tags" tokenSeparators={[',','，',';','；']} placeholder="例如：版式、品牌、信息可视化" options={['版式','品牌','插画','信息可视化','交互设计','设计研究'].map(t=>({value:t,label:t}))}/></Form.Item>
          <Form.Item name="skilled_courses" label="擅长课程" rules={[{required:true,type:'array',min:1,message:'至少选择或填写一门擅长课程'}]} extra="可从开放课程和课程库中选择，也可输入课程名称后回车；不等于本次选课志愿。"><Select aria-label="擅长课程" mode="tags" tokenSeparators={[',','，',';','；']} showSearch placeholder="选择或输入擅长课程" options={courses.map(name=>({value:name,label:name}))}/></Form.Item>
          <Form.Item name="participating_course_ids" label="参与课程组" extra="可多选全部专业课；名称相同的课程按编码区分。此项为本人申报，不代替管理员核实的团队记录，也不等于本次选课志愿。"><Select aria-label="参与课程组" mode="multiple" allowClear showSearch optionFilterProp="label" placeholder="选择参与的课程组（可多选）" options={courseGroups.map(c=>({value:c.id,label:`${c.name}（${c.course_code}）${c.department?` · ${c.department}`:''}`}))}/></Form.Item>
          <Form.Item name="introduction" label="专业经历与个人说明"><Input.TextArea rows={4} maxLength={2000} showCount placeholder="可填写研究方向、教学经验或相关实践经历"/></Form.Item>
          <Space wrap><Form.Item name="contact_email" label="联系邮箱"><Input maxLength={200}/></Form.Item><Form.Item name="contact_phone" label="联系电话"><Input maxLength={50}/></Form.Item></Space>
          <Space wrap><Button loading={busy} onClick={()=>void save(false)}>保存资料</Button><Button type="primary" loading={busy} onClick={()=>void save(true)}>保存并进入选课</Button></Space>
        </Form>
      </Card>
    </>}
  </Space>;
}
