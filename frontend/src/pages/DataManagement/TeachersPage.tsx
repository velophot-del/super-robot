// 教师管理页面（含查看已排课程 + 只读课程归属）
import { useState } from 'react';
import {
  Form, Input, InputNumber, Select, Button, Drawer, Table, Descriptions,
  Statistic, Row, Col, Empty, message, Tag, Typography,
  Divider, Alert, Spin,
} from 'antd';
import { EyeOutlined, SettingOutlined } from '@ant-design/icons';
import DataTable from '../../components/DataTable';
import { ImportButton } from '../../components/DataImport';
import { teacherApi } from '../../api/client';
import type { TeacherCoursesResponse, TeacherCourseInfo, TeacherCourseAffiliations } from '../../types';

const { Text } = Typography;

export default function TeachersPage() {
  const [tableKey, setTableKey] = useState(0);
  // ---- 查看已排课程 ----
  const [courseDrawerOpen, setCourseDrawerOpen] = useState(false);
  const [selectedTeacher, setSelectedTeacher] = useState<{ id: number; name: string; department?: string; title?: string } | null>(null);
  const [teacherCourses, setTeacherCourses] = useState<TeacherCoursesResponse | null>(null);
  const [coursesLoading, setCoursesLoading] = useState(false);

  // ---- 查看课程归属（只读） ----
  const [affiliationDrawerOpen, setAffiliationDrawerOpen] = useState(false);
  const [affiliationTeacher, setAffiliationTeacher] = useState<any>(null);
  const [affiliations, setAffiliations] = useState<TeacherCourseAffiliations | null>(null);
  const [affiliationLoading, setAffiliationLoading] = useState(false);

  const handleViewCourses = async (record: any) => {
    setSelectedTeacher({ id: record.id, name: record.name, department: record.department, title: record.title });
    setCourseDrawerOpen(true);
    setCoursesLoading(true);
    try {
      const res = await teacherApi.getCourses(record.id) as TeacherCoursesResponse;
      setTeacherCourses(res);
    } catch (e: any) {
      message.error(`加载课程失败: ${e.message}`);
      setTeacherCourses(null);
    } finally {
      setCoursesLoading(false);
    }
  };

  const handleOpenAffiliations = async (record: any) => {
    setAffiliationTeacher(record);
    setAffiliationDrawerOpen(true);
    setAffiliationLoading(true);
    setAffiliations(null);
    try {
      const res = await teacherApi.getCourseAffiliations(record.id) as TeacherCourseAffiliations;
      setAffiliations(res);
    } catch (e: any) {
      message.error(`加载课程归属失败: ${e.message}`);
    } finally {
      setAffiliationLoading(false);
    }
  };

  const courseColumns = [
    { title: '课程名称', dataIndex: 'course_name', key: 'course_name', width: 130 },
    { title: '课程编码', dataIndex: 'course_code', key: 'course_code', width: 90 },
    { title: '授课班级', dataIndex: 'class_name', key: 'class_name', width: 100, render: (v: string) => <Tag color="purple">{v}</Tag> },
    { title: '学期次数', dataIndex: 'semester_sessions', key: 'semester_sessions', width: 65 },
    { title: '周次数', dataIndex: 'weekly_sessions', key: 'weekly_sessions', width: 55 },
    { title: '每次课时', dataIndex: 'hours_per_session', key: 'hours_per_session', width: 65 },
    { title: '总课时', dataIndex: 'total_hours', key: 'total_hours', width: 55, render: (v: number | null) => v ?? '-' },
    { title: '周排课次数', dataIndex: 'time_slots', key: 'time_slots', width: 75 },
  ];

  const affiliationColumns = [
    { title: '课程名称', dataIndex: 'name', key: 'name' },
    { title: '课程编码', dataIndex: 'course_code', key: 'course_code', width: 120 },
    { title: '所属专业', dataIndex: 'department', key: 'department', width: 140, render: (v: string | null) => v || '未设置' },
    { title: '课程性质', dataIndex: 'course_type', key: 'course_type', width: 110, render: (v: string | null) => v ? <Tag>{v}</Tag> : '-' },
  ];

  return (
    <>
      <DataTable
        key={tableKey}
        title="教师管理"
        entityType="teachers"
        api={teacherApi}
        extraToolbar={<ImportButton entityType="teachers" onImported={() => setTableKey(k => k + 1)} />}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 60 },
          { title: '姓名', dataIndex: 'name', width: 90 },
          { title: '工号', dataIndex: 'teacher_code', width: 100 },
          { title: '部门', dataIndex: 'department', width: 120 },
          { title: '职称', dataIndex: 'title', width: 100 },
          { title: '职位', dataIndex: 'position', width: 130, render: (value: string) => value || '教师' },
          { title: '审核专业方向', dataIndex: 'review_major', width: 130 },
          { title: '邮箱', dataIndex: 'email', width: 160 },
          { title: '每周最大课时', dataIndex: 'max_weekly_hours', width: 100 },
        ]}
        formFields={() => (
          <>
            <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
              <Input placeholder="教师姓名" />
            </Form.Item>
            <Form.Item name="teacher_code" label="工号" rules={[{ required: true }]}>
              <Input placeholder="教师工号/编号" />
            </Form.Item>
            <Form.Item name="department" label="所属部门">
              <Input placeholder="如: 数学教研组" />
            </Form.Item>
            <Form.Item name="title" label="职称">
              <Select options={['教授', '副教授', '讲师', '助教', '高级教师', '一级教师'].map(t => ({ label: t, value: t }))} />
            </Form.Item>
            <Form.Item name="position" label="职位" initialValue="教师">
              <Select options={['教师', '教研室主任', '教研室副主任', '院长', '副院长'].map(value => ({label: value, value}))} />
            </Form.Item>
            <Form.Item noStyle shouldUpdate={(before, after) => before.position !== after.position}>
              {({getFieldValue}) => ['教研室主任', '教研室副主任'].includes(getFieldValue('position')) ? (
                <Form.Item name="review_major" label="审核专业方向" rules={[{required: true, message: '请选择审核专业方向'}]}>
                  <Select options={['视觉传达设计', '包装设计', '智能交互设计', '数字艺术', '时尚传播'].map(value => ({label: value, value}))} />
                </Form.Item>
              ) : null}
            </Form.Item>
            <Form.Item name="email" label="邮箱">
              <Input placeholder="email@school.edu.cn" />
            </Form.Item>
            <Form.Item name="phone" label="电话">
              <Input placeholder="联系电话" />
            </Form.Item>
            <Form.Item name="max_weekly_hours" label="每周最大课时">
              <InputNumber min={2} max={40} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="remarks" label="备注">
              <Input.TextArea rows={2} />
            </Form.Item>
          </>
        )}
        extraRowActions={(record) => (
          <>
            <Button
              type="link"
              size="small"
              icon={<SettingOutlined />}
              onClick={() => handleOpenAffiliations(record)}
              style={{ color: '#f59e0b' }}
            >
              分配课程
            </Button>
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => handleViewCourses(record)}
              style={{ color: '#533afd' }}
            >
              旧排课记录
            </Button>
          </>
        )}
      />

      {/* ===== Drawer 1: 查看已排课表 ===== */}
      <Drawer
        title={selectedTeacher ? `${selectedTeacher.name} - 旧系统排课记录` : '旧系统排课记录'}
        open={courseDrawerOpen}
        onClose={() => setCourseDrawerOpen(false)}
        width={620}
        destroyOnClose
      >
        {selectedTeacher && (
          <Descriptions size="small" column={2} style={{ marginBottom: 20 }}>
            <Descriptions.Item label="教师">{selectedTeacher.name}</Descriptions.Item>
            <Descriptions.Item label="部门">{selectedTeacher.department || '未设置'}</Descriptions.Item>
            <Descriptions.Item label="职称">{selectedTeacher.title || '未设置'}</Descriptions.Item>
          </Descriptions>
        )}
        <Alert type="info" showIcon style={{ marginBottom: 16 }} title="此处仅显示旧版排课记录"
          description="新排课周期的授课安排请在“历史课表”或教师本人“我的课表”中查看。" />

        {teacherCourses && teacherCourses.courses.length > 0 ? (
          <>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Statistic title="课程门数" value={teacherCourses.courses.length} suffix="门" valueStyle={{ color: '#533afd' }} />
              </Col>
              <Col span={12}>
                <Statistic title="每周总课时" value={teacherCourses.total_weekly_hours} suffix="学时" valueStyle={{ color: '#10b981' }} />
              </Col>
            </Row>
            <Table
              dataSource={teacherCourses.courses}
              columns={courseColumns}
              rowKey={(r: TeacherCourseInfo) => `${r.course_id}-${r.class_name}`}
              loading={coursesLoading}
              pagination={false}
              size="small"
              style={{ border: '1px solid #e3e8ee', borderRadius: 8 }}
            />
          </>
        ) : (
          <Empty description={coursesLoading ? '加载中...' : '该教师暂无排课记录，请先执行排课'} style={{ marginTop: 60 }} />
        )}
      </Drawer>

      {/* ===== Drawer 2: 课程归属（只读） ===== */}
      <Drawer
        title={affiliationTeacher ? `${affiliationTeacher.name} - 课程归属` : '课程归属'}
        open={affiliationDrawerOpen}
        onClose={() => setAffiliationDrawerOpen(false)}
        width={720}
        destroyOnClose
        footer={<div style={{ textAlign: 'right' }}><Button onClick={() => setAffiliationDrawerOpen(false)}>关闭</Button></div>}
      >
        {affiliationTeacher && (
          <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
            <Descriptions.Item label="教师">{affiliationTeacher.name}</Descriptions.Item>
            <Descriptions.Item label="部门">{affiliationTeacher.department || '未设置'}</Descriptions.Item>
          </Descriptions>
        )}
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="此处只读展示，不再勾选分配课程"
          description="所属课程组来自教师个人资料中的“参与课程组”；专业课程负责人来自课程管理中的“课程负责人”设置。"
        />

        {affiliationLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin tip="加载课程归属..." /></div>
        ) : (
          <>
            <Divider titlePlacement="start">所属课程组（教师个人资料）</Divider>
            {affiliations?.course_groups.length ? (
              <Table
                dataSource={affiliations.course_groups}
                columns={affiliationColumns}
                rowKey="id"
                pagination={false}
                size="small"
                style={{ border: '1px solid #e3e8ee', borderRadius: 8 }}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={affiliations?.profile_updated ? '教师尚未在个人资料中申报参与课程组' : '教师尚未完善个人资料'}
              />
            )}

            <Divider titlePlacement="start">专业课程负责人（课程管理）</Divider>
            {affiliations?.leader_courses.length ? (
              <Table
                dataSource={affiliations.leader_courses}
                columns={affiliationColumns}
                rowKey="id"
                pagination={false}
                size="small"
                style={{ border: '1px solid #e3e8ee', borderRadius: 8 }}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂未担任专业课程负责人" />
            )}
            <Text type="secondary" style={{ display: 'block', marginTop: 16, fontSize: 12 }}>
              课程负责人由管理员在“课程管理”中设置；参与课程组由教师本人在“个人资料”中维护。
            </Text>
          </>
        )}
      </Drawer>
    </>
  );
}
