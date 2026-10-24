import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Tabs, Typography, Upload, message } from 'antd';
import { Link, useSearchParams } from 'react-router-dom';
import { DownloadOutlined, EditOutlined, InboxOutlined, PlusOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import { classApi, ioApi } from '../../api/client';
import { planningApi } from '../../api/planning';
import { gradeLabel, normalizeCohort } from '../../lib/adminStageGrid';

const { Dragger } = Upload;

async function loadAllClasses(){
  const rows:any[]=[];let skip=0;
  while(skip<10000){const page=await classApi.list({skip,limit:500}) as any[];rows.push(...page);if(page.length<500)break;skip+=page.length;}
  return rows;
}
export default function ProgramsGradesPage(){
  const [searchParams]=useSearchParams();
  const [programs,setPrograms]=useState<any[]>([]),[units,setUnits]=useState<any[]>([]),[directions,setDirections]=useState<any[]>([]),[classes,setClasses]=useState<any[]>([]),[loading,setLoading]=useState(false),[saving,setSaving]=useState(false);
  const [open,setOpen]=useState(false),[editing,setEditing]=useState<any>(null),[directionOpen,setDirectionOpen]=useState(false),[directionEditing,setDirectionEditing]=useState<any>(null);
  const [form]=Form.useForm();
  const [directionForm]=Form.useForm();
  const [importOpen,setImportOpen]=useState(false),[importFile,setImportFile]=useState<File|null>(null),[importPreview,setImportPreview]=useState<any>(null),[importBusy,setImportBusy]=useState(false),[templateBusy,setTemplateBusy]=useState(false);
  const load=useCallback(async()=>{setLoading(true);try{const [p,u,d,c]=await Promise.all([planningApi.programs(),planningApi.offeringUnits(),planningApi.directions(),loadAllClasses()]);setPrograms(p);setUnits(u);setDirections(d);setClasses(c);}catch(e){message.error(e instanceof Error?e.message:'专业、教研室或班级目录加载失败');}finally{setLoading(false);}},[]);
  useEffect(()=>{void load();},[load]);
  const cohorts=useMemo(()=>{const map=new Map<string,any[]>();for(const row of classes){const key=normalizeCohort(row.grade)||'待补录';map.set(key,[...(map.get(key)||[]),row]);}return [...map].sort(([a],[b])=>b.localeCompare(a,'zh-CN')).map(([cohort,rows])=>({cohort,count:rows.length,active:rows.filter(row=>row.is_active!==false).length,majors:[...new Set(rows.map(row=>row.department).filter(Boolean))].join('、')}));},[classes]);
  const startCreate=()=>{setEditing(null);form.resetFields();form.setFieldsValue({duration_semesters:8,education_level:'本科',is_active:true});setOpen(true);};
  const startEdit=(row:any)=>{setEditing(row);form.setFieldsValue({duration_semesters:row.duration_semesters,education_level:row.education_level,degree_category:row.degree_category,construction_level:row.construction_level,source_notes:row.source_notes,is_active:row.is_active});setOpen(true);};
  const save=async()=>{setSaving(true);try{const values=await form.validateFields();if(editing)await planningApi.updateProgram(editing.id,values);else await planningApi.createProgram(values);message.success(editing?'专业目录已更新':'专业已新增');setOpen(false);form.resetFields();setEditing(null);await load();}catch(e){if(e instanceof Error)message.error(e.message);}finally{setSaving(false);}};
  const [unitOpen,setUnitOpen]=useState(false),[unitEditing,setUnitEditing]=useState<any>(null);
  const [unitForm]=Form.useForm();
  const startUnitCreate=()=>{setUnitEditing(null);unitForm.resetFields();setUnitOpen(true);};
  const startUnitEdit=(row:any)=>{setUnitEditing(row);unitForm.setFieldsValue({code:row.code,name:row.name});setUnitOpen(true);};
  const saveUnit=async()=>{setSaving(true);try{const values=await unitForm.validateFields();if(unitEditing)await planningApi.renameOfferingUnit(unitEditing.id,values.name);else await planningApi.createOfferingUnit(values);message.success(unitEditing?'教研室名称已更新':'教研室已新增');setUnitOpen(false);unitForm.resetFields();setUnitEditing(null);await load();}catch(e){if(e instanceof Error)message.error(e.message);}finally{setSaving(false);}};
  const startDirectionCreate=()=>{setDirectionEditing(null);directionForm.resetFields();directionForm.setFieldsValue({entry_type:'专业方向',source_order:directions.length+1});setDirectionOpen(true);};
  const startDirectionEdit=(row:any)=>{setDirectionEditing(row);directionForm.setFieldsValue({program_id:row.program_id,name:row.name,entry_type:row.entry_type,offering_unit_id:row.offering_unit_id,notes:row.notes,source_order:row.source_order});setDirectionOpen(true);};
  const saveDirection=async()=>{setSaving(true);try{const values=await directionForm.validateFields();if(directionEditing)await planningApi.updateDirection(directionEditing.id,values);else await planningApi.createDirection(values);message.success(directionEditing?'方向信息已更新':'招生方向已新增');setDirectionOpen(false);directionForm.resetFields();setDirectionEditing(null);await load();}catch(e){if(e instanceof Error)message.error(e.message);}finally{setSaving(false);}};
  const unitPrograms=(unitId:number)=>[...new Set(directions.filter(d=>d.offering_unit_id===unitId).map(d=>`${d.program_name}（${d.program_code}）`))].join('、')||'未关联';
  const downloadCatalogTemplate=async()=>{setTemplateBusy(true);try{const result=await ioApi.downloadAcademicCatalogXlsxTemplate() as Blob;const blob=result instanceof Blob?result:new Blob([result],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='专业方向与专业代码目录模板.xlsx';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){message.error(e instanceof Error?e.message:'模板下载失败');}finally{setTemplateBusy(false);}};
  const openCatalogImport=()=>{setImportFile(null);setImportPreview(null);setImportOpen(true);};
  const previewCatalogImport=async()=>{if(!importFile)return;setImportBusy(true);try{setImportPreview(await ioApi.previewAcademicCatalogXlsx(importFile));}catch(e){message.error(e instanceof Error?e.message:'Excel预览失败');}finally{setImportBusy(false);}};
  const confirmCatalogImport=async()=>{if(!importPreview)return;setImportBusy(true);try{const result:any=await ioApi.confirmAcademicCatalogXlsx(importPreview.preview_id,importPreview.token);message.success(result.summary);setImportPreview(null);setImportFile(null);await load();}catch(e){message.error(e instanceof Error?e.message:'确认导入失败');}finally{setImportBusy(false);}};
  return <Space direction="vertical" size={16} style={{width:'100%'}}>
    <div><Typography.Title level={3}>专业方向与教研室管理</Typography.Title><Typography.Text type="secondary">按专业代码管理学位、学制和建设信息，并维护专业方向/招生口径与对应教研室。班级届次仍在班级管理中维护。</Typography.Text></div>
    <Alert showIcon type="warning" title="目录依据所给工作簿初始化。数字媒体艺术方向数、部分专业建设级别/批复年度及智能工程与创意设计教研室归属在表内有口径差异，备注已保留待核实；请以学校正式文件为准。" action={<Link to="/data/classes"><Button>进入班级 / 届次管理</Button></Link>}/>
    <Tabs defaultActiveKey={searchParams.get('tab')==='units'?'units':searchParams.get('tab')==='directions'?'directions':'programs'} items={[
      {key:'programs',label:`专业目录（${programs.length}）`,children:<Card title="标准专业目录" extra={<Space><Button icon={<DownloadOutlined/>} loading={templateBusy} onClick={()=>void downloadCatalogTemplate()}>下载Excel模板</Button><Button icon={<UploadOutlined/>} onClick={openCatalogImport}>导入Excel</Button><Button icon={<ReloadOutlined/>} onClick={()=>void load()} loading={loading}>刷新</Button><Button type="primary" icon={<PlusOutlined/>} onClick={startCreate}>新增专业</Button></Space>}>
      <Table rowKey="id" loading={loading} dataSource={programs} pagination={{pageSize:10}} columns={[
        {title:'专业代码',dataIndex:'code',width:120},
        {title:'专业名称',dataIndex:'name',width:180},
        {title:'学历 / 学位',width:130,render:(_:unknown,row:any)=>`${row.education_level||'本科'} / ${row.degree_category||'待补充'}`},
        {title:'学制',dataIndex:'duration_semesters',width:90,render:(v:number)=>`${Math.floor(v/2)}年（${v}学期）`},
        {title:'方向数',dataIndex:'direction_count',width:80},
        {title:'专业建设级别',dataIndex:'construction_level',ellipsis:true},
        {title:'状态',dataIndex:'is_active',width:100,render:(v:boolean)=><Tag color={v?'green':'default'}>{v?'启用':'停用'}</Tag>},
        {title:'操作',width:100,render:(_:unknown,row:any)=><Button type="link" icon={<EditOutlined/>} onClick={()=>startEdit(row)}>设置</Button>},
      ]}/>
      </Card>},
      {key:'directions',label:`方向 / 招生口径（${directions.length}）`,children:<Card title="专业方向与教研室对应关系" extra={<Space><Button icon={<DownloadOutlined/>} loading={templateBusy} onClick={()=>void downloadCatalogTemplate()}>下载导入模板</Button><Button icon={<UploadOutlined/>} onClick={openCatalogImport}>导入目录 Excel</Button><Button icon={<ReloadOutlined/>} onClick={()=>void load()} loading={loading}>刷新</Button><Button type="primary" icon={<PlusOutlined/>} onClick={startDirectionCreate}>新增记录</Button></Space>}>
        <Table rowKey="id" loading={loading} dataSource={directions} pagination={{pageSize:10}} columns={[
          {title:'专业',width:210,render:(_:unknown,row:any)=><>{row.program_name}<br/><Typography.Text type="secondary">{row.program_code}</Typography.Text></>},
          {title:'方向 / 招生口径',dataIndex:'name',width:230},
          {title:'记录类型',dataIndex:'entry_type',width:120,render:(v:string)=><Tag color={v==='专业方向'?'blue':'purple'}>{v}</Tag>},
          {title:'对应教研室',dataIndex:'offering_unit_name',width:220,render:(v:string)=>v||<Tag color="orange">待关联</Tag>},
          {title:'备注 / 核实事项',dataIndex:'notes',ellipsis:true},
          {title:'操作',width:130,render:(_:unknown,row:any)=><Space><Button type="link" icon={<EditOutlined/>} onClick={()=>startDirectionEdit(row)}>编辑</Button><Popconfirm title="删除这条方向记录？" onConfirm={async()=>{try{await planningApi.deleteDirection(row.id);message.success('已删除');await load();}catch(e){message.error(e instanceof Error?e.message:'删除失败');}}}><Button type="link" danger>删除</Button></Popconfirm></Space>},
        ]}/>
      </Card>},
      {key:'units',label:`开课教研室（${units.length}）`,children:<Card title="教研室目录" extra={<Space><Button icon={<ReloadOutlined/>} onClick={()=>void load()} loading={loading}>刷新</Button><Button type="primary" icon={<PlusOutlined/>} onClick={startUnitCreate}>新增教研室</Button></Space>}>
        <Table rowKey="id" loading={loading} dataSource={units} pagination={false} columns={[
          {title:'目录编码',dataIndex:'code',width:150},
          {title:'教研室名称',dataIndex:'name'},
          {title:'负责专业方向',width:300,render:(_:unknown,row:any)=>unitPrograms(row.id)},
          {title:'状态',dataIndex:'is_active',width:100,render:(v:boolean)=><Tag color={v?'green':'default'}>{v?'启用':'停用'}</Tag>},
          {title:'操作',width:120,render:(_:unknown,row:any)=><Button type="link" icon={<EditOutlined/>} onClick={()=>startUnitEdit(row)}>修改名称</Button>},
        ]}/>
      </Card>},
      {key:'cohorts',label:`年级 / 班级（${classes.length}）`,children:<Card title={`班级届次概览（${classes.length}个班级）`} extra={<Link to="/data/classes">管理班级数据</Link>}>
      <Table rowKey="cohort" dataSource={cohorts} pagination={false} locale={{emptyText:'暂无班级数据'}} columns={[
        {title:'届次',dataIndex:'cohort',width:130,render:(v:string)=>v==='待补录'?v:gradeLabel(v)},
        {title:'班级数',dataIndex:'count',width:100},
        {title:'纳入排课',dataIndex:'active',width:110},
        {title:'所属专业',dataIndex:'majors',render:(v:string)=>v||'未填写'},
      ]}/>
    </Card>},
    ]}/>
    <Modal title={editing?'设置专业档案':'新增标准专业'} open={open} onCancel={()=>setOpen(false)} onOk={()=>void save()} confirmLoading={saving} okText={editing?'保存设置':'新增专业'} width={620}>
      <Form form={form} layout="vertical">
        {!editing&&<><Form.Item name="code" label="专业编码" rules={[{required:true,whitespace:true}]}><Input maxLength={50}/></Form.Item><Form.Item name="name" label="专业名称" rules={[{required:true,whitespace:true}]}><Input maxLength={100}/></Form.Item></>}
        <Form.Item name="education_level" label="学历层次" rules={[{required:true}]}><Select options={['本科','专科','硕士研究生','博士研究生'].map(value=>({value}))}/></Form.Item>
        <Form.Item name="degree_category" label="授予学位"><Select allowClear options={['艺术学','工学','文学','教育学','管理学'].map(value=>({value}))}/></Form.Item>
        <Form.Item name="duration_semesters" label="标准学制" rules={[{required:true}]}><InputNumber min={1} max={20} addonAfter="学期" style={{width:'100%'}}/></Form.Item>
        <Form.Item name="construction_level" label="专业建设级别"><Input maxLength={300}/></Form.Item>
        <Form.Item name="source_notes" label="来源备注 / 待核实事项"><Input.TextArea rows={3} maxLength={1000}/></Form.Item>
        {editing&&<Form.Item name="is_active" label="启用状态" valuePropName="checked"><Switch checkedChildren="启用" unCheckedChildren="停用"/></Form.Item>}
      </Form>
    </Modal>
    <Modal title={unitEditing?'修改教研室名称':'新增教研室'} open={unitOpen} onCancel={()=>setUnitOpen(false)} onOk={()=>void saveUnit()} confirmLoading={saving} okText={unitEditing?'保存名称':'新增'}>
      <Form form={unitForm} layout="vertical">
        {!unitEditing&&<Form.Item name="code" label="目录编码" rules={[{required:true}]}><Input placeholder="如 DEPT-06"/></Form.Item>}
        <Form.Item name="name" label="教研室名称" rules={[{required:true,whitespace:true}]}><Input maxLength={100}/></Form.Item>
      </Form>
    </Modal>
    <Modal title={directionEditing?'编辑方向 / 招生口径':'新增方向 / 招生口径'} open={directionOpen} onCancel={()=>setDirectionOpen(false)} onOk={()=>void saveDirection()} confirmLoading={saving} width={620}>
      <Form form={directionForm} layout="vertical">
        <Form.Item name="program_id" label="所属专业" rules={[{required:true}]}><Select showSearch optionFilterProp="label" options={programs.map(p=>({value:p.id,label:`${p.name}（${p.code}）`}))}/></Form.Item>
        <Form.Item name="name" label="方向名称 / 招生口径" rules={[{required:true,whitespace:true}]}><Input maxLength={150}/></Form.Item>
        <Form.Item name="entry_type" label="记录类型" rules={[{required:true}]}><Select options={[{value:'专业方向',label:'专业方向'},{value:'整专业招生',label:'整专业招生'}]}/></Form.Item>
        <Form.Item name="offering_unit_id" label="对应教研室"><Select allowClear showSearch optionFilterProp="label" options={units.map(u=>({value:u.id,label:u.name}))}/></Form.Item>
        <Form.Item name="notes" label="备注 / 核实事项"><Input.TextArea rows={3} maxLength={1000}/></Form.Item>
        <Form.Item name="source_order" label="排序"><InputNumber min={0} style={{width:'100%'}}/></Form.Item>
      </Form>
    </Modal>
    <Modal title="导入专业方向与教研室目录" open={importOpen} onCancel={()=>setImportOpen(false)} footer={null} width={1000} destroyOnHidden>
      <Space direction="vertical" size={14} style={{width:'100%'}}>
        <Alert type="info" showIcon message="使用学院专业目录 Excel 的两个工作表格式。先预览校验，再确认写入；新增和更新项会显示在预览中，重复记录不会重复创建。"/>
        <Space><Button icon={<DownloadOutlined/>} loading={templateBusy} onClick={()=>void downloadCatalogTemplate()}>下载 Excel 模板</Button><Dragger accept=".xlsx" maxCount={1} showUploadList={Boolean(importFile)} beforeUpload={file=>{setImportFile(file);setImportPreview(null);return false;}} onRemove={()=>{setImportFile(null);setImportPreview(null);}} style={{width:420,padding:8}}><p className="ant-upload-drag-icon"><InboxOutlined/></p><p className="ant-upload-text">选择或拖入专业目录 .xlsx 文件</p></Dragger><Button type="primary" icon={<UploadOutlined/>} disabled={!importFile} loading={importBusy} onClick={()=>void previewCatalogImport()}>预览校验</Button></Space>
        {importPreview&&<>
          <Alert type={importPreview.counts.invalid?'warning':'success'} showIcon message={`新增 ${importPreview.counts.new} · 更新 ${importPreview.counts.update} · 无变化 ${importPreview.counts.unchanged} · 需处理 ${importPreview.counts.invalid}`} description="预览阶段不会修改目录。确认后新增或更新专业、方向和教研室关联；令牌30分钟有效且只能确认一次。"/>
          {!!importPreview.parse_errors?.length&&<Alert type="error" showIcon message="文件解析问题" description={<ul>{importPreview.parse_errors.map((x:string,i:number)=><li key={i}>{x}</li>)}</ul>}/>}
          {!!importPreview.warnings?.length&&<Alert type="warning" showIcon message="来源表内口径或名称提示" description={<ul>{importPreview.warnings.map((x:string,i:number)=><li key={i}>{x}</li>)}</ul>}/>}
          <Table rowKey={(_:unknown,row:any)=>`${row.kind}-${row.code}-${row.name}`} dataSource={importPreview.rows} pagination={{pageSize:8}} scroll={{x:850}} columns={[
            {title:'类型',dataIndex:'kind',width:130},{title:'专业代码',dataIndex:'code',width:120},{title:'专业 / 方向名称',dataIndex:'name',width:230},{title:'对应教研室',dataIndex:'unit',width:210,render:(v:string)=>v||'未设置'},
            {title:'状态',dataIndex:'status',width:100,render:(v:string)=><Tag color={v==='new'?'green':v==='update'?'blue':v==='unchanged'?'default':'red'}>{{new:'新增',update:'更新',unchanged:'无变化',invalid:'需处理'}[v]||v}</Tag>},
            {title:'问题',dataIndex:'issues',render:(v:string[])=>v?.join('；')||'—'},
          ]}/>
          <Button type="primary" disabled={importPreview.counts.new+importPreview.counts.update===0} loading={importBusy} onClick={()=>void confirmCatalogImport()}>确认导入有效记录</Button>
        </>}
      </Space>
    </Modal>
  </Space>;
}
