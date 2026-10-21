import { useEffect, useState } from 'react';
import { Alert, Button, InputNumber, Space, Table, Tag, Typography, message } from 'antd';
import { planningApi } from '../api/planning';

type WeightItem = { key: string; name: string; description: string; default: number; weight: number };

export default function MatchWeightsPanel({ plan, disabled, onSaved }: { plan: any; disabled: boolean; onSaved: () => Promise<void> }) {
  const items: WeightItem[] = plan.match_weight_items || [];
  const [weights, setWeights] = useState<Record<string, number>>(plan.match_weights || {});
  const [saving, setSaving] = useState(false);
  useEffect(() => { setWeights(plan.match_weights || {}); }, [plan.id, JSON.stringify(plan.match_weights || {})]);
  const total = items.reduce((sum, item) => sum + (weights[item.key] ?? 0), 0);
  const changed = items.some(item => (weights[item.key] ?? 0) !== (plan.match_weights?.[item.key] ?? 0));
  const mismatch = Boolean(plan.match?.weights) && items.some(item => (plan.match.weights[item.key] ?? 0) !== (plan.match_weights?.[item.key] ?? 0));
  const save = async () => {
    if (total <= 0) { message.warning('匹配权重合计必须大于 0'); return; }
    setSaving(true);
    try {
      await planningApi.saveMatchWeights(plan.id, weights);
      message.success('匹配权重已保存，下一次匹配生效');
      await onSaved();
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存匹配权重失败');
    } finally { setSaving(false); }
  };
  return <>
    <Space wrap style={{ marginBottom: 12 }}>
      <Typography.Text strong>系统匹配项目与权重</Typography.Text>
      <Tag color="purple">合计 {total} 分</Tag>
      {changed && <Tag color="orange">权重尚未保存</Tag>}
      <Button type="primary" size="small" loading={saving} disabled={disabled || plan.state === 'published' || !changed} onClick={() => void save()}>保存权重</Button>
    </Space>
    {plan.state === 'published' && <Alert type="info" showIcon title="周期已发布，匹配权重已冻结" style={{ marginBottom: 12 }} />}
    {mismatch && <Alert type="warning" showIcon title="当前权重与最近一次匹配批次不同，请重新运行匹配" style={{ marginBottom: 12 }} />}
    <Table rowKey="key" dataSource={items} pagination={false} size="small" style={{ marginBottom: 16 }}
      columns={[
        { title: '匹配项目', dataIndex: 'name', width: 130 },
        { title: '说明', dataIndex: 'description' },
        { title: '默认', dataIndex: 'default', width: 70 },
        { title: '权重', width: 130, render: (_, item: WeightItem) => <InputNumber aria-label={`${item.name}权重`} min={0} max={100}
          value={weights[item.key] ?? item.weight} disabled={disabled || plan.state === 'published'}
          onChange={value => setWeights(old => ({ ...old, [item.key]: Number(value ?? 0) }))} style={{ width: 100 }} /> },
      ]} />
    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
      权重只影响综合推荐分；专业适配度仍按方向和领域单独计算。修改权重不会使教师已提交的志愿失效，保存后请重新运行匹配。
    </Typography.Text>
  </>;
}
