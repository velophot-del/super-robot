// 课程管理页面（含总课时自动计算）
import { useEffect, useState, useMemo, useCallback } from 'react';
import type { FormInstance } from 'antd';
import { Form, Input, InputNumber, Select, Switch, Space, Button, Alert } from 'antd';
import DataTable from '../../components/DataTable';
import { courseApi, teacherApi } from '../../api/client';
import { filterCourses, courseFilterOptions, loadAllCourses } from '../../lib/courseFilters';
import type { CourseFilters } from '../../lib/courseFilters';

export default function CoursesPage() {
  const [teachers,setTeachers]=useState<any[]>([]);
  const [teacherError,setTeacherError]=useState('');
  const [teacherLoading,setTeacherLoading]=useState(true);
  const loadTeachers=useCallback(async()=>{
    setTeacherLoading(true);setTeacherError('');
    try{setTeachers(await loadAllCourses(teacherApi.list));}
    catch(e){setTeacherError(e instanceof Error?e.message:'教师名单读取失败');}
    finally{setTeacherLoading(false);}
  },[]);
  useEffect(()=>{void loadTeachers();},[loadTeachers]);
  const [filters, setFilters] = useState<CourseFilters>({});
  const [catalog, setCatalog] = useState<any[]>([]);
  const options = useMemo(() => courseFilterOptions(catalog), [catalog]);
  const api = useMemo(() => ({...courseApi, list: async (params?: any) => {
    // Load every page so categories and filtering include the complete catalog.
    const rows = await loadAllCourses(courseApi.list);
    setCatalog(rows);
    return params?.search ? rows.filter(r => r.name.includes(params.search)) : rows;
  }}), []);
  const filterData = useCallback((rows: any[]) => filterCourses(rows, filters), [filters]);
  return (<>
    {teacherError&&<Alert type="error" showIcon title={`课程负责人教师名单加载失败：${teacherError}`} action={<Button onClick={()=>void loadTeachers()}>重试</Button>} style={{marginBottom:16}}/>}
    <Space wrap style={{marginBottom:16}}>
      {([['department','专业'],['category','课程性质'],['course_type','类型'],['cohort','入学届次']] as const).map(([key,label]) =>
        <Select key={key} aria-label={`按${label}筛选`} placeholder={`全部${label}`} allowClear showSearch
          style={{minWidth:160}} value={filters[key]} onChange={value => setFilters(old => ({...old,[key]:value}))}
          options={[...options[key].map(value => ({value,label:key==='cohort'?`${value}级`:value})),{value:'__unset__',label:'未设置'}]}/>
      )}
      <Button onClick={() => setFilters({})}>重置筛选</Button>
    </Space>
    <Alert type="info" showIcon style={{marginBottom:16}} title="年级按入学届次筛选；课程性质与届次取自培养方案来源，无来源的课程显示未设置。"/>
    <DataTable
      title="课程管理"
      entityType="courses"
      api={api}
      filterData={filterData}
      columns={[
        { title: 'ID', dataIndex: 'id', width: 60 },
        { title: '课程名称', dataIndex: 'name', width: 160 },
        { title: '课程编码', dataIndex: 'course_code', width: 100 },
        { title: '课程负责人', width:160, render:(_:unknown,r:any)=>r.leader_teacher_name?`${r.leader_teacher_name}（${r.leader_teacher_code}）`:'未指定' },
        { title: '所属专业', dataIndex: 'department', width: 100, render: (v: string) => v || <span style={{color:'#ccc'}}>未设置</span> },
        { title: '课程性质', render: (_:unknown,r:any) => [...new Set((r.curriculum_sources||[]).filter((s:any)=>(!filters.department||filters.department==='__unset__'||s.major===filters.department)&&(!filters.cohort||filters.cohort==='__unset__'||s.cohort===filters.cohort)).map((s:any)=>s.metadata?.category).filter(Boolean))].join('、')||'未设置' },
        { title: '入学届次', render: (_:unknown,r:any) => [...new Set((r.curriculum_sources||[]).filter((s:any)=>(!filters.department||filters.department==='__unset__'||s.major===filters.department)&&(!filters.category||filters.category==='__unset__'||s.metadata?.category===filters.category)).map((s:any)=>s.cohort).filter(Boolean))].map(v=>`${v}级`).join('、')||'未设置' },
        { title: '类型', dataIndex: 'course_type', width: 80 },
        { title: '授课周数', width: 85, render: (_:unknown,r:any) => r.curriculum_sources?.[0]?.metadata.teaching_weeks??'待配置' },
        
        
        { title: '总课时', dataIndex: 'total_hours', width: 70, render: (v: number|null) => v ?? '-' },
        { title: '学分', dataIndex: 'credits', width: 60 },
        { title: '需连排', dataIndex: 'requires_consecutive', width: 70, render: (v: boolean) => v ? '是' : '否' },
        { title: '需实验室', dataIndex: 'requires_lab', width: 80, render: (v: boolean) => v ? '是' : '否' },
      ]}
      formFields={form => <CourseFields form={form} teachers={teachers} teacherLoading={teacherLoading} teacherError={teacherError} />}
    />
  </>);
}

function CourseFields({ form,teachers,teacherLoading,teacherError }: { form: FormInstance;teachers:any[];teacherLoading:boolean;teacherError:string }) {
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
            <Form.Item name="course_type" label="课程类型">
              <Select options={['必修','选修','公共课','实践课'].map(t => ({ label: t, value: t }))} />
            </Form.Item>
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
