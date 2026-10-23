// 课程管理页面（含总课时自动计算）
import { useEffect, useState, useMemo, useCallback } from 'react';
import type { FormInstance } from 'antd';
import { Form, Input, InputNumber, Select, Switch, Space, Button, Alert, Modal, Popconfirm, message, Tabs, Collapse } from 'antd';
import { useNavigate } from 'react-router-dom';
import DataTable from '../../components/DataTable';
import { courseApi, teacherApi } from '../../api/client';
import { filterCourses, courseFilterOptions, loadAllCourses, currentGradeCohorts, courseCohorts, inGrade } from '../../lib/courseFilters';
import type { CourseFilters } from '../../lib/courseFilters';
import { gradeLabel } from '../../lib/adminStageGrid';
import { planningApi } from '../../api/planning';

const GRADE_COHORTS = currentGradeCohorts();

export default function CoursesPage() {
  const navigate=useNavigate();
  const [teachers,setTeachers]=useState<any[]>([]);
  const [teacherError,setTeacherError]=useState('');
  const [units,setUnits]=useState<any[]>([]);
  const [teacherLoading,setTeacherLoading]=useState(true);
  const loadTeachers=useCallback(async()=>{
    setTeacherLoading(true);setTeacherError('');
    try{setTeachers(await loadAllCourses(teacherApi.list));}
    catch(e){setTeacherError(e instanceof Error?e.message:'教师名单读取失败');}
    finally{setTeacherLoading(false);}
  },[]);
  useEffect(()=>{void loadTeachers();},[loadTeachers]);
  useEffect(()=>{void planningApi.offeringUnits().then(setUnits).catch(()=>setUnits([]));},[]);
  const [filters, setFilters] = useState<CourseFilters>({});
  const [gradeTab,setGradeTab]=useState<string>(GRADE_COHORTS[0]);
  const [includeInactive,setIncludeInactive]=useState(false);
  const [includePublic,setIncludePublic]=useState(false);
  const [catalog, setCatalog] = useState<any[]>([]);
  const [tableKey,setTableKey]=useState(0),[selectedRows,setSelectedRows]=useState<any[]>([]),[bulkOpen,setBulkOpen]=useState(false),[bulkBusy,setBulkBusy]=useState(false);
  const [bulkForm]=Form.useForm();
  const [unitForm]=Form.useForm();
  const [unitOpen,setUnitOpen]=useState(false),[unitBusy,setUnitBusy]=useState(false);
  const options = useMemo(() => courseFilterOptions(catalog), [catalog]);
  const api = useMemo(() => ({...courseApi, list: async (params?: any) => {
    // Load every page so categories and filtering include the complete catalog.
    const rows = await loadAllCourses(params=>courseApi.list({...params,include_inactive:includeInactive,include_public:includePublic}));
    setCatalog(rows);
    return params?.search ? rows.filter(r => r.name.includes(params.search)) : rows;
  }}), [includeInactive,includePublic]);
  const filterData = useCallback((rows: any[]) =>
    filterCourses(rows, filters).filter(row => inGrade(row, gradeTab)), [filters, gradeTab]);
  const refresh=()=>setTableKey(value=>value+1);
  const bulkUpdate=async()=>{
    const raw=bulkForm.getFieldsValue();
    const updates=Object.fromEntries(Object.entries(raw).filter(([,value])=>value!==undefined)
      .map(([key,value])=>[key,value==='__clear__'?null:value]));
    if(!Object.keys(updates).length){message.warning('请选择至少一个批量修改字段');return;}
    setBulkBusy(true);
    try{await courseApi.bulkUpdate(selectedRows.map(row=>row.id),updates);message.success(`已批量修改${selectedRows.length}门课程`);setBulkOpen(false);setSelectedRows([]);refresh();}
    catch(e){message.error(e instanceof Error?e.message:'批量修改失败');}
    finally{setBulkBusy(false);}
  };
  const addUnit=async()=>{
    setUnitBusy(true);
    try{const values=await unitForm.validateFields();await planningApi.createOfferingUnit(values);unitForm.resetFields();setUnits(await planningApi.offeringUnits());setUnitOpen(false);message.success('开课单位已新增');}
    catch(e){if(e instanceof Error)message.error(e.message);}
    finally{setUnitBusy(false);}
  };
  return (<>
    {teacherError&&<Alert type="error" showIcon title={`课程负责人教师名单加载失败：${teacherError}`} action={<Button onClick={()=>void loadTeachers()}>重试</Button>} style={{marginBottom:16}}/>}
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12,marginBottom:12}}>
      <div style={{display:'flex',alignItems:'center',gap:12}}>
        <span style={{fontWeight:600}}>年级</span>
        <Tabs type="card" activeKey={gradeTab} onChange={setGradeTab}
          items={GRADE_COHORTS.map(cohort => ({key: cohort, label: `${cohort}级`}))} style={{marginBottom:0}}/>
      </div>
      <span style={{color:'#8c8c8c',fontSize:12}}>每个页签展示该届学生培养方案中的全部课程（含 4 年学期）</span>
    </div>
    <Space wrap style={{marginBottom:16}}>
      {([['course_type','课程类型'],['category','课程性质'],['department','专业']] as const).map(([key,label]) =>
        <Select key={key} aria-label={`按${label}筛选`} placeholder={`全部${label}`} allowClear showSearch
          style={{minWidth:160}} value={filters[key]} onChange={value => setFilters(old => ({...old,[key]:value}))}
          options={[...options[key].map(value => ({value,label:value})),{value:'__unset__',label:'未设置'}]}/>
      )}
      <Button onClick={() => setFilters({})}>重置筛选</Button>
    </Space>
    <Collapse ghost size="small" style={{marginBottom:16}} items={[{
      key: 'help', label: '课程库说明',
      children: '排课周期直接读取课程库；课程按适用年级、专业和上课学期匹配。公共课（学科通识课、德育通识课）默认不进入课程库列表与排课池。导入课程请使用本页的批量导入。'
    }]}/>
    <DataTable
      key={tableKey}
      title="课程管理"
      entityType="courses"
      api={api}
      filterData={filterData}
      columns={[
        { title: 'ID', dataIndex: 'id', width: 60 },
        { title: '课程名称', dataIndex: 'name', width: 160 },
        { title: '课程编码', dataIndex: 'course_code', width: 100 },
        { title: '状态', dataIndex: 'is_active', width: 80, render: (v:boolean) => v===false?<span style={{color:'#8c8c8c'}}>已移出</span>:'活动' },
        { title: '课程负责人', width:160, render:(_:unknown,r:any)=>r.leader_teacher_name?`${r.leader_teacher_name}（${r.leader_teacher_code}）`:'未指定' },
        { title: '适用专业', dataIndex: 'department', width: 100, render: (v: string) => v || <span style={{color:'#ccc'}}>通用课程</span> },
        { title: '开课单位', dataIndex: 'offering_unit_name', width: 120, render: (v:string) => v || '未设置' },
        { title: '课程类型', dataIndex: 'course_type', width: 120 },
        { title: '上课学期', dataIndex: 'semester', width: 100, render: (v:number|null|undefined) => v?`第${v}学期`:'待补录' },
        { title: '课程性质', dataIndex: 'course_nature', width: 90 },
        { title: '年级', dataIndex: 'cohort', width: 90, render: (_:unknown, r:any) => {
            const cohorts = courseCohorts(r);
            return cohorts.length ? cohorts.map(gradeLabel).join('、') : '不限';
        } },
        { title: '授课周数', dataIndex: 'teaching_weeks', width: 85, render: (v:number|null) => v??'按学期次数' },
        { title: '总课时', dataIndex: 'total_hours', width: 70, render: (v: number|null) => v ?? '-' },
        { title: '学分', dataIndex: 'credits', width: 60 },
        { title: '需连排', dataIndex: 'requires_consecutive', width: 70, render: (v: boolean) => v ? '是' : '否' },
        { title: '需实验室', dataIndex: 'requires_lab', width: 80, render: (v: boolean) => v ? '是' : '否' },
      ]}
      formFields={form => <CourseFields form={form} teachers={teachers} teacherLoading={teacherLoading} teacherError={teacherError} units={units} />}
      extraToolbar={<><Switch checked={includeInactive} checkedChildren="含已移出" unCheckedChildren="仅活动" onChange={value=>{setIncludeInactive(value);refresh();}}/><Switch checked={includePublic} checkedChildren="含公共课" unCheckedChildren="隐藏公共课" onChange={value=>{setIncludePublic(value);refresh();}}/><Button onClick={()=>navigate('/data/import?entity=courses')}>批量导入</Button><Button onClick={()=>setUnitOpen(true)}>开课单位</Button></>}
      extraRowActions={record=>record.is_active===false?<Button type="link" size="small" onClick={async()=>{try{await courseApi.update(record.id,{is_active:true});message.success('课程已恢复到活动课程库');refresh();}catch(e){message.error(e instanceof Error?e.message:'恢复失败');}}}>恢复</Button>:null}
      bulkActions={(rows,clearSelection)=><Space wrap><span>已选 {rows.length} 门</span><Button onClick={()=>{setSelectedRows(rows);bulkForm.resetFields();setBulkOpen(true);}}>批量修改</Button><Popconfirm title={`将${rows.length}门课程移出活动课程库？历史课表保留，可在课程表中恢复。`} onConfirm={async()=>{setBulkBusy(true);try{await courseApi.bulkRemove(rows.map(row=>row.id));message.success(`已移出${rows.length}门课程`);clearSelection();setSelectedRows([]);refresh();}catch(e){message.error(e instanceof Error?e.message:'批量移出失败');}finally{setBulkBusy(false);}}} okText="移出课程库" cancelText="取消"><Button danger loading={bulkBusy}>批量移出</Button></Popconfirm></Space>}
    />
    <Modal title={`批量修改 ${selectedRows.length} 门课程`} open={bulkOpen} onCancel={()=>setBulkOpen(false)} onOk={()=>void bulkUpdate()} confirmLoading={bulkBusy} okText="应用修改" destroyOnClose>
      <Form form={bulkForm} layout="vertical">
        <Form.Item name="course_type" label="课程类型"><Select allowClear placeholder="不修改" options={['专业课','学科通识课','德育通识课','综合实践课','跨专业交叉课','国际课程'].map(value=>({value,label:value}))}/></Form.Item>
        <Form.Item name="course_nature" label="课程性质"><Select allowClear placeholder="不修改" options={['必修课','限选课','任选课'].map(value=>({value,label:value}))}/></Form.Item>
        <Form.Item name="semester" label="上课学期"><Select allowClear placeholder="不修改" options={Array.from({length:12},(_,i)=>({value:i+1,label:`第${i+1}学期`}))}/></Form.Item>
        <Form.Item name="cohort" label="适用年级"><Select allowClear showSearch placeholder="不修改" options={[{value:'__clear__',label:'不限年级'},...options.cohort.map(value=>({value,label:gradeLabel(value)}))]}/></Form.Item>
        <Form.Item name="department" label="适用专业"><Select allowClear showSearch placeholder="不修改" options={[{value:'__clear__',label:'通用课程'},...options.department.map(value=>({value,label:value}))]}/></Form.Item>
        <Form.Item name="offering_unit_id" label="开课单位"><Select allowClear showSearch placeholder="不修改" options={[{value:'__clear__',label:'清空开课单位'},...units.map(unit=>({value:unit.id,label:unit.name}))]}/></Form.Item>
        <Form.Item name="teaching_weeks" label="授课周数"><InputNumber min={1} max={20} style={{width:'100%'}} placeholder="不修改"/></Form.Item>
        <Form.Item name="is_active" label="课程状态"><Select allowClear placeholder="不修改" options={[{value:true,label:'纳入课程库'},{value:false,label:'停用'}]}/></Form.Item>
      </Form>
    </Modal>
    <Modal title="新增开课单位" open={unitOpen} onCancel={()=>setUnitOpen(false)} onOk={()=>void addUnit()} confirmLoading={unitBusy} destroyOnClose>
      <Form form={unitForm} layout="vertical"><Form.Item name="code" label="单位编码" rules={[{required:true}]}><Input/></Form.Item><Form.Item name="name" label="开课单位名称" rules={[{required:true}]}><Input/></Form.Item></Form>
    </Modal>
  </>);
}

function CourseFields({ form,teachers,teacherLoading,teacherError,units }: { form: FormInstance;teachers:any[];teacherLoading:boolean;teacherError:string;units:any[] }) {
        // 监听学期教学次数和每次课时变化，自动计算总课时
        const semesterSessions = Form.useWatch('semester_sessions', form);
        const hoursPerSession = Form.useWatch('hours_per_session', form);

        useEffect(() => {
          if ((form.isFieldTouched('semester_sessions')||form.isFieldTouched('hours_per_session')) && semesterSessions != null && hoursPerSession != null) {
            const calculated = semesterSessions * hoursPerSession;
            form.setFieldValue('total_hours', calculated);
          }
        }, [semesterSessions, hoursPerSession, form]);

        return (
          <>
            <Form.Item name="name" label="课程名称" rules={[{ required: true }]}>
              <Input placeholder="如: 高等数学" />
            </Form.Item>
            <Form.Item name="course_code" label="课程编码" rules={[{ required: true }]}>
              <Input placeholder="如: MATH101" />
            </Form.Item>
            <Form.Item name="leader_teacher_id" label="课程负责人" getValueFromEvent={value=>value??null} extra="由管理员指定一位教师，可留空或清除；此项不会自动分配授课任务。">
              <Select aria-label="课程负责人" allowClear showSearch optionFilterProp="label" loading={teacherLoading} disabled={teacherLoading||Boolean(teacherError)} placeholder="选择一位课程负责人" options={teachers.map(t=>({value:t.id,label:`${t.name}（${t.teacher_code}）`}))}/>
            </Form.Item>
            <Form.Item name="offering_unit_id" label="开课单位">
              <Select allowClear placeholder="选择承担教学的单位" options={units.map(u=>({value:u.id,label:u.name}))}/>
            </Form.Item>
            <Form.Item name="course_type" label="课程类型" rules={[{required:true}]}>
              <Select options={['专业课','学科通识课','德育通识课','综合实践课','跨专业交叉课','国际课程'].map(t => ({ label: t, value: t }))} />
            </Form.Item>
            <Form.Item name="course_nature" label="课程性质" rules={[{required:true}]}>
              <Select options={['必修课','限选课','任选课'].map(t => ({ label: t, value: t }))} />
            </Form.Item>
            <Form.Item name="semester" label="上课学期" rules={[{required:true,message:'请选择上课学期'}]}>
              <Select placeholder="选择课程上课学期" options={Array.from({length:12},(_,i)=>({value:i+1,label:`第${i+1}学期`}))} />
            </Form.Item>
            <Form.Item name="cohort" label="适用年级"><Input placeholder="如：2026；留空表示适用于所有匹配年级"/></Form.Item>
            <Form.Item name="teaching_weeks" label="授课周数"><InputNumber min={1} max={20} style={{width:'100%'}} placeholder="留空按学期教学次数"/></Form.Item>
            <Form.Item name="semester_sessions" label="学期教学次数" rules={[{ required: true }]} help="一学期总共上几次课">
              <InputNumber min={1} max={40} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="weekly_sessions" label="每周上课次数" help="每周排几个时间段">
              <InputNumber min={1} max={8} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="hours_per_session" label="每次课时" help="一次课等于几学时，通常为2">
              <InputNumber min={1} max={6} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="total_hours"
              label="总课时"
              help="自动计算（学期教学次数 × 每次课时），可手动修改"
            >
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="credits" label="学分">
              <InputNumber min={0} max={30} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="requires_consecutive" label="需要连排" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="requires_lab" label="需要实验室" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="department" label="所属专业" help="与班级的「所属专业」一致时，该课程优先分配给对应班级">
              <Input placeholder="如: 人工智能/理科/文科（留空则为通用课）" />
            </Form.Item>
            <Form.Item name="remarks" label="备注">
              <Input.TextArea rows={2} />
            </Form.Item>
          </>
        );
}
