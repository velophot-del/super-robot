import { useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Empty, Modal, Select, Tag, Tooltip, Typography, message } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { weekDates } from '../lib/selectionGrid';
import { stageLanes } from '../lib/adminStageGrid';

type Props = {
  plan: any;
  tasks: any[];
  match: any;
  busy: boolean;
  canAssign: boolean;
  reason: string;
  onAssign: (task: any, teacherIds: number[]) => void;
};

const CARD_HEIGHT = 140;
const LANE_HEIGHT = 150;

export default function ReviewTimetable({ plan, tasks, match, busy, canAssign, reason, onAssign }: Props) {
  const [editing, setEditing] = useState<any>(null);
  const [value, setValue] = useState<number[]>([]);
  const weeks = Number(plan.weeks) || 20;
  const placed = tasks.filter(task => task.start_week && task.end_week);
  const majorOf = (task: any) => task.major || task.department || plan.major || task.source?.major || '未注明专业';
  const cohortOf = (task: any) => task.cohort || plan.cohort || '';
  const groups = new Map<string, { major: string; cohort: string; group: string; tasks: any[] }>();
  for (const task of placed) {
    const key = `${majorOf(task)}|${cohortOf(task)}|${task.group}`;
    if (!groups.has(key)) groups.set(key, { major: majorOf(task), cohort: cohortOf(task), group: task.group, tasks: [] });
    groups.get(key)!.tasks.push(task);
  }
  const rows = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b, 'zh-CN'));
  const candidatesFor = (task: any) => (match?.candidates || []).filter((candidate: any) => candidate.task_id === task.id);

  useEffect(() => { if (editing) setValue(editing.teacher_ids || []); }, [editing]);
  const open = (task: any) => { setEditing(task); setValue(task.teacher_ids || []); };
  const applicants = editing?.applicants || [];
  const options: { value: number; label: string; disabled: boolean }[] = applicants.map((applicant: any) => {
    const candidate = candidatesFor(editing).find((item: any) => item.teacher_id === applicant.teacher_id);
    return {
      value: applicant.teacher_id,
      label: candidate
        ? `${applicant.teacher_name} · ${candidate.eligible ? '可审核' : (candidate.reasons || []).join('；') || '不符合条件'}${candidate.normalized_total != null ? ` · ${candidate.normalized_total}%` : ''}`
        : applicant.teacher_name,
      disabled: Boolean(candidate && !candidate.eligible && !(editing?.teacher_ids || []).includes(applicant.teacher_id)),
    };
  });
  // 兼容历史任务：当前已分配教师即使不在本批次申报列表中，也要能正常显示。
  (editing?.teacher_ids || []).forEach((teacherId: number, index: number) => {
    if (!options.some(option => option.value === teacherId)) {
      options.push({ value: teacherId, label: editing.teacher_names?.[index] || `教师${teacherId}`, disabled: false });
    }
  });
  const current = editing?.teacher_names?.length ? editing.teacher_names.join('、') : '待审核';
  const canSave = canAssign && !busy && applicants.length > 0 && value.length === editing?.teacher_count && Boolean(reason.trim());
  const save = () => {
    if (!editing || !canSave) return;
    onAssign(editing, value);
    setEditing(null);
  };

  if (!placed.length) return <Empty description="暂无已排周段的课程任务，配置周段后可在此人工调剂" />;
  return <>
    <div style={{ overflowX: 'auto', border: '1px solid #d9d9e3', borderRadius: 8 }}>
      <table aria-label="全学院实时课表" style={{ borderCollapse: 'collapse', width: '100%', minWidth: 200 + weeks * 120 }}>
        <colgroup><col style={{ width: 200 }} />{Array.from({ length: weeks }, (_, index) => <col key={index} style={{ width: 120 }} />)}</colgroup>
        <thead><tr style={{ background: '#f3f4f6' }}>
          <th style={{ border: '1px solid #d9d9e3', padding: 8 }}>专业 / 年级 / 教学组</th>
          {Array.from({ length: weeks }, (_, index) => <th key={index} style={{ border: '1px solid #d9d9e3', padding: '5px 2px', fontSize: 12 }}>
            第{index + 1}周<div style={{ fontWeight: 400, fontSize: 12 }}>{weekDates(plan.start_date, index + 1)}</div>
          </th>)}
        </tr></thead>
        <tbody>{rows.map(([key, group]) => {
          const bars = stageLanes(group.tasks);
          const height = Math.max(LANE_HEIGHT, ...bars.map(bar => (bar.lane + 1) * LANE_HEIGHT));
          return <tr key={key}>
            <th style={{ border: '1px solid #d9d9e3', padding: 8, textAlign: 'left', verticalAlign: 'top' }}>
              <div>{group.major}</div>
              <Typography.Text type="secondary">{group.cohort ? `${group.cohort}级 · ` : ''}{group.group}</Typography.Text>
            </th>
            <td colSpan={weeks} style={{ border: '1px solid #d9d9e3', padding: 0 }}>
              <div style={{ position: 'relative', height }}>
                {Array.from({ length: weeks }, (_, index) => <div key={index} style={{ position: 'absolute', left: `${index * 100 / weeks}%`, width: `${100 / weeks}%`, height: '100%', borderRight: '1px solid #eee' }} />)}
                {bars.map(({ task, lane }) => {
                  const names = (task.applicants || []).map((applicant: any) => applicant.teacher_name).join('、') || '暂无';
                  const assigned = task.teacher_names?.length ? task.teacher_names.join('、') : '待审核';
                  const left = `${(task.start_week - 1) * 100 / weeks}%`;
                  const width = `${(task.end_week - task.start_week + 1) * 100 / weeks}%`;
                  return <div key={task.id} style={{
                    position: 'absolute', left, width, top: lane * LANE_HEIGHT + 5, height: CARD_HEIGHT,
                    background: task.locked ? '#edf3fa' : '#fff7e8', border: `1px solid ${task.locked ? '#b5c5d8' : '#f0b35b'}`,
                    borderRadius: 6, padding: 6, boxSizing: 'border-box', overflow: 'auto', zIndex: 1,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 4 }}>
                      <Typography.Text strong style={{ fontSize: 14 }}>{task.name}</Typography.Text>
                      <Tag color={task.locked ? 'green' : 'orange'} style={{ marginInlineEnd: 0 }}>{task.locked ? '已审核' : '待审核'}</Tag>
                    </div>
                    <div style={{ fontSize: 12, color: '#64748d', marginTop: 2 }}>W{task.start_week}—W{task.end_week} · 需{task.teacher_count}名教师</div>
                    <Tooltip title={names}><div style={{ fontSize: 12, marginTop: 3 }}>申报 {task.applicant_count ?? task.applicants?.length ?? 0} 人：{names}</div></Tooltip>
                    <div style={{ fontSize: 12, marginTop: 2 }}>当前：{assigned}</div><div style={{fontSize:12}}>{task.room_name||'未分配'}</div>
                    <Button size="small" type="link" icon={<EditOutlined />} disabled={!canAssign || !(task.applicants?.length)} onClick={() => open(task)} style={{ padding: 0, height: 22, fontSize: 12 }}>
                      人工调剂
                    </Button>
                  </div>;
                })}
              </div>
            </td>
          </tr>;
        })}</tbody>
      </table>
    </div>

    <Modal title={editing ? `人工调剂 · ${editing.name}` : '人工调剂'} open={Boolean(editing)} onCancel={() => setEditing(null)} onOk={save}
      okText="保存调剂" confirmLoading={busy} okButtonProps={{ disabled: !canSave }} width={520}>
      {editing && <>
        <Descriptions size="small" column={1} bordered items={[
          { key: 'group', label: '教学组', children: editing.group },
          { key: 'weeks', label: '授课周段', children: `W${editing.start_week}—W${editing.end_week}` },
          { key: 'applicants', label: '申报教师', children: applicants.length ? applicants.map((item: any) => item.teacher_name).join('、') : '暂无教师申报' },
          { key: 'current', label: '当前教师', children: current },
        ]} style={{ marginBottom: 16 }} />
        {!canAssign && <Alert type="warning" showIcon title="请先运行系统匹配" description="匹配完成后才能保存人工调剂。" style={{ marginBottom: 12 }} />}
        <Select mode="multiple" aria-label="人工调剂教师" value={value} onChange={values => {
          if (values.length > editing.teacher_count) { message.warning(`最多选择 ${editing.teacher_count} 名教师`); return; }
          setValue(values);
        }} options={options} style={{ width: '100%' }} placeholder={`请选择 ${editing.teacher_count} 名申报教师`} disabled={!canAssign || !applicants.length} />
        <Typography.Paragraph type="secondary" style={{ margin: '10px 0 0', fontSize: 12 }}>
          需选择 {editing.teacher_count} 名教师；调剂说明使用上方“调剂说明”，填写后保存。仅允许选择本批次已提交且符合硬约束的教师。
        </Typography.Paragraph>
      </>}
    </Modal>
  </>;
}
