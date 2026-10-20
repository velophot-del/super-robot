import { useEffect, useState } from 'react';
import { Alert, Button, Select, Space, Tag, message } from 'antd';
import { debugApi, DEMO_TOKEN_KEY } from '../api/client';
import type { DemoTeacher } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export default function DebugToolbar() {
  const { user, demoEnabled, switchDemo } = useAuth();
  const [teachers, setTeachers] = useState<DemoTeacher[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (demoEnabled && user?.is_demo) {
      debugApi.identities().then(data => setTeachers(data.teachers))
        .catch((e: Error) => message.error(e.message));
    }
  }, [demoEnabled, user?.is_demo]);
  if (!demoEnabled || !user?.is_demo) return null;
  const change = async (role: 'admin' | 'teacher', teacherId?: number) => {
    setBusy(true);
    try { await switchDemo(role, teacherId); }
    catch (e) { message.error(e instanceof Error ? e.message : '切换失败'); setBusy(false); }
  };
  return <Alert type="warning" showIcon style={{ borderRadius: 0 }} title={
    <Space wrap>
      <Tag color="orange">DEBUG 演示模式</Tag>
      <span>当前身份：{user.role === 'admin' ? '管理员' : `教师 · ${user.username}`}</span>
      <Select<'admin' | 'teacher'> aria-label="切换演示身份" value={user.role === 'teacher' ? 'teacher' : 'admin'} disabled={busy} style={{ width: 120 }}
        options={[{ value: 'admin', label: '管理员' }, { value: 'teacher', label: '教师', disabled: !teachers.length }]}
        onChange={role => change(role, role === 'teacher' ? teachers[0]?.id : undefined)} />
      {user.role === 'teacher' && <Select aria-label="切换演示教师" value={user.teacher_id}
        disabled={busy} style={{ minWidth: 180 }} options={teachers.map(t => ({ value: t.id, label: t.name }))}
        onChange={id => change('teacher', id)} />}
      <Button size="small" onClick={() => { sessionStorage.removeItem(DEMO_TOKEN_KEY); window.location.assign('/login'); }}>退出演示</Button>
    </Space>} />;
}
