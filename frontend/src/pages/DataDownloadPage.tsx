// 管理员数据下载中心
import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Select, Space, Table, Tag, Typography, message } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { DATASET_LABELS } from '../lib/download';
import { downloadApi } from '../api/downloads';
import type { DownloadDataset, DownloadOptions } from '../api/downloads';

const { Title, Paragraph, Text } = Typography;

const DESCRIPTIONS: Record<DownloadDataset, string> = {
  classes: '全部班级基础数据（年级、专业、人数、班主任等）',
  teachers: '全部教师数据（工号、部门、职称、职位、审核方向等）',
  courses: '全部课程数据（编码、类型、学期、计划周数、学时、负责人等）',
  classrooms: '全部教室数据（容量、类型、多媒体、可用状态等）',
  schedule: '可选任意周期：已发布优先用快照；草稿/开放/匹配中按当前任务导出；无任务时输出空白表',
  all: '一个工作簿包含班级、教师、课程、教室与课表',
};
const stateNames: Record<string,string> = {draft:'草稿',open:'开放填报',matched:'匹配中',published:'已发布'};

export default function DataDownloadPage() {
  const [options, setOptions] = useState<DownloadOptions>();
  const [planId, setPlanId] = useState<number>();
  const [busy, setBusy] = useState<DownloadDataset | 'options'>();

  const [error,setError]=useState('');
  const loadOptions=useCallback(async()=>{
    setError('');
    try{setOptions(await downloadApi.options());}
    catch(e){setError(e instanceof Error?e.message:'读取下载选项失败');}
  },[]);
  useEffect(()=>{void loadOptions();},[loadOptions]);

  const download = async (dataset: DownloadDataset) => {
    setBusy(dataset);
    try {
      const blob = await downloadApi.fetch(
        dataset, dataset === 'schedule' || dataset === 'all' ? planId : undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const label = options?.datasets.find(item => item.key === dataset)?.label || dataset;
      a.download = `${label}_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      message.success('下载已开始');
    } catch (e) {
      message.error(e instanceof Error ? e.message : '下载失败');
    } finally {
      setBusy(undefined);
    }
  };

  const datasets = options?.datasets || Object.entries(DATASET_LABELS).map(([key,label])=>({key:key as DownloadDataset,label}));
  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={3}>数据下载</Title>
      <Paragraph type="secondary">
        管理员可下载班级、教师、课程、教室与课表数据，全部导出为 Excel 工作簿。
      </Paragraph>
      {error&&<Alert type="error" showIcon title={error} action={<Button onClick={()=>void loadOptions()}>重新加载</Button>} style={{marginBottom:16}}/>}
      <Alert type="info" showIcon style={{ marginBottom: 16 }} title="课表数据说明"
        description={options?.plans?.length
          ? '可选择任意排课周期（含草稿、过程稿和空白稿）；已发布周期优先使用不可变快照，未选择时取最新周期。选择「全部数据」时会一并导出课表。'
          : options?.legacy_schedule
            ? `当前没有排课周期，课表将回退到旧版最新排课版本 ${options.legacy_schedule}。`
            : '当前没有排课周期或旧版排课数据，课表将输出空白表头。'} />
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Text strong>课表周期</Text>
          <Select allowClear placeholder="最新周期课表" style={{ minWidth: 300 }} value={planId}
            onChange={setPlanId} options={(options?.plans || []).map(plan => ({
              value: plan.id,
              label: `${plan.name}${plan.state ? ` · ${stateNames[plan.state] || plan.state}` : ''}`,
            }))} />
          <Button type="primary" icon={<DownloadOutlined />} loading={busy === 'all'}
            onClick={() => void download('all')}>下载全部数据</Button>
        </Space>
      </Card>
      <Table rowKey="key" dataSource={datasets} pagination={false} columns={[
        { title: '数据', dataIndex: 'label', width: 150, render: (value: string) => <Tag color="blue">{value}</Tag> },
        { title: '内容', render: (_: unknown, row: { key: DownloadDataset }) => <Text type="secondary">{DESCRIPTIONS[row.key]}</Text> },
        { title: '操作', width: 120, render: (_: unknown, row: { key: DownloadDataset }) => (
          <Button icon={<DownloadOutlined />} loading={busy === row.key}
            onClick={() => void download(row.key)}>下载</Button>
        ) },
      ]} />
    </div>
  );
}
