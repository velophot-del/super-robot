import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Form, Input, Modal, Space, Table, Tag, Typography, message } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { planningApi } from '../../api/planning';

type Unit = {id:number;code:string;name:string;is_active:boolean};

export default function OfferingUnitsPage(){
  const [rows,setRows]=useState<Unit[]>([]),[loading,setLoading]=useState(false),[saving,setSaving]=useState(false);
  const [open,setOpen]=useState(false),[editing,setEditing]=useState<Unit|null>(null);
  const [form]=Form.useForm();
  const load=useCallback(async()=>{setLoading(true);try{setRows(await planningApi.offeringUnits());}catch(e){message.error(e instanceof Error?e.message:'教研室目录加载失败');}finally{setLoading(false);}},[]);
  useEffect(()=>{void load();},[load]);
  const startCreate=()=>{setEditing(null);form.resetFields();setOpen(true);};
  const startEdit=(row:Unit)=>{setEditing(row);form.setFieldsValue({code:row.code,name:row.name});setOpen(true);};
  const save=async()=>{setSaving(true);try{const v=await form.validateFields();if(editing)await planningApi.renameOfferingUnit(editing.id,v.name);else await planningApi.createOfferingUnit(v);message.success(editing?'教研室名称已更新':'教研室已新增');setOpen(false);setEditing(null);form.resetFields();await load();}catch(e){if(e instanceof Error)message.error(e.message);}finally{setSaving(false);}};
  return <Space direction="vertical" size={16} style={{width:'100%'}}>
    <div><Typography.Title level={3}>开课单位 / 教研室管理</Typography.Title><Typography.Text type="secondary">系统默认五个教研室。名称修改后同步教师管理中的同名部门，课程关联保留原目录记录。</Typography.Text></div>
    <Alert showIcon type="info" title="教师部门与课程开课单位共用本目录。目录编码保持稳定；改名不会改变课程关联。"/>
    <Card title={`教研室目录（${rows.length}）`} extra={<Space><Button icon={<ReloadOutlined/>} onClick={()=>void load()}>刷新</Button><Button type="primary" icon={<PlusOutlined/>} onClick={startCreate}>新增教研室</Button></Space>}>
      <Table rowKey="id" loading={loading} dataSource={rows} pagination={false} columns={[
        {title:'目录编码',dataIndex:'code',width:150},
        {title:'教研室名称',dataIndex:'name'},
        {title:'状态',dataIndex:'is_active',width:100,render:(v:boolean)=><Tag color={v?'green':'default'}>{v?'启用':'停用'}</Tag>},
        {title:'操作',width:110,render:(_:unknown,row:Unit)=><Button type="link" icon={<EditOutlined/>} onClick={()=>startEdit(row)}>修改名称</Button>},
      ]}/>
    </Card>
    <Modal title={editing?'修改教研室名称':'新增教研室'} open={open} onCancel={()=>setOpen(false)} onOk={()=>void save()} confirmLoading={saving} okText={editing?'保存名称':'新增'}>
      <Form form={form} layout="vertical">
        {!editing&&<Form.Item name="code" label="目录编码" rules={[{required:true}]}><Input placeholder="如 DEPT-06"/></Form.Item>}
        <Form.Item name="name" label="教研室名称" rules={[{required:true,whitespace:true}]}><Input maxLength={100}/></Form.Item>
      </Form>
    </Modal>
  </Space>;
}
