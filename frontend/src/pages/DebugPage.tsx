import { useEffect, useState } from 'react';
import { Alert, Button, Card, Select, Space, Spin, Typography, message } from 'antd';
import { Link } from 'react-router-dom';
import { debugApi } from '../api/client';
import type { DemoTeacher } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export default function DebugPage() {
  const { loading, demoEnabled, switchDemo } = useAuth();
  const [teachers, setTeachers] = useState<DemoTeacher[]>([]);
  const [teacherId, setTeacherId] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!demoEnabled) return;
    debugApi.identities().then(({ teachers: data }) => {
      setTeachers(data);
      setTeacherId(data[0]?.id);
    }).catch((e: Error) => setError(e.message));
  }, [demoEnabled]);

  const enter = async (role: 'admin' | 'teacher') => {
    setBusy(true);
    try { await switchDemo(role, role === 'teacher' ? teacherId : undefined); }
    catch (e) { message.error(e instanceof Error ? e.message : '身份切换失败'); setBusy(false); }
  };

  return <main style={{ maxWidth: 760, margin: '64px auto', padding: 24 }}>
    <Typography.Title level={2}>Debug 演示模式</Typography.Title>
    <Typography.Paragraph>无需账号密码，选择身份即可进入本地演示系统。</Typography.Paragraph>
    {loading ? <Spin tip="检查演示模式" /> : !demoEnabled ?
      <Alert type="info" showIcon title="演示模式未启用" description="请联系管理员开启本地演示，或使用正常登录入口。" /> :
      <Space orientation="vertical" size="large" style={{ width: '100%' }}>
        <Alert type="warning" showIcon title="独立演示数据 · 身份模拟"
          description="教师可从课程池预选、保存草稿并提交意愿；系统评分后由有权人员审核。管理员可管理周期、阶段任务及教师专业画像。" />
        {error && <Alert type="error" showIcon title={error} />}
        <Card title="管理员">
          <Typography.Paragraph>配置周期与课程任务，维护专业画像，运行匹配并审核分配。</Typography.Paragraph>
          <Button type="primary" loading={busy} onClick={() => enter('admin')}>以管理员身份进入</Button>
        </Card>
        <Card title="教师">
          <Typography.Paragraph>选择具体教师，进入课程预选、草稿提交和本人匹配结果。</Typography.Paragraph>
          <Space wrap>
            <Select aria-label="演示教师" value={teacherId} onChange={setTeacherId}
              style={{ minWidth: 220 }} placeholder="暂无教师，请先录入演示教师"
              options={teachers.map(t => ({ value: t.id, label: `${t.name}（${t.teacher_code}）` }))} />
            <Button type="primary" disabled={!teacherId} loading={busy} onClick={() => enter('teacher')}>以教师身份进入</Button>
          </Space>
        </Card>
      </Space>}
    <Typography.Paragraph style={{ marginTop: 24 }}><Link to="/login">使用正常登录</Link></Typography.Paragraph>
  </main>;
}
