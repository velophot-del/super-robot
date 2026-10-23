// AI 服务配置：服务商、模型、加密密钥与连通性测试
import { useEffect, useState } from 'react';
import {
  Alert, AutoComplete, Button, Card, Checkbox, Form, Input, Select, Space, Spin,
  Switch, Tag, Typography, message,
} from 'antd';
import { SaveOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { aiApi } from '../api/ai';
import type { AIConfigInput, AIConfigState, AIProvider } from '../api/ai';

const { Title, Paragraph, Text } = Typography;

const MODEL_SUGGESTIONS: Record<AIProvider, string[]> = {
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  qwen: ['qwen-plus', 'qwen-turbo', 'qwen-max'],
  moonshot: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
  zhipu: ['glm-4-flash', 'glm-4-plus', 'glm-4-air'],
  custom: [],
  anthropic: ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'],
};

export default function AISettingsPage() {
  const [form] = Form.useForm();
  const [config, setConfig] = useState<AIConfigState>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [clearKey, setClearKey] = useState(false);
  const provider = Form.useWatch('provider', form) as AIProvider | undefined;

  const load = async () => {
    try {
      const data = await aiApi.getConfig();
      setConfig(data);
      form.setFieldsValue({
        provider: data.provider, base_url: data.base_url, model: data.model,
        api_key: '', enabled: data.enabled,
      });
      setClearKey(false);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '读取 AI 配置失败');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const save = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const data: AIConfigInput = { ...values, api_key: values.api_key || '', clear_key: clearKey };
      const next = await aiApi.saveConfig(data);
      setConfig(next);
      form.setFieldValue('api_key', '');
      setClearKey(false);
      message.success('AI 配置已保存');
    } catch (e: any) {
      if (e?.message) message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    try {
      const values = await form.validateFields();
      setTesting(true);
      const result = await aiApi.testConfig({
        provider: values.provider, base_url: values.base_url, model: values.model,
        api_key: values.api_key || '',
      });
      if (result.ok) {
        message.success(`${result.message}${result.model ? ` · ${result.model}` : ''}${result.latency_ms != null ? `（${result.latency_ms}ms）` : ''}`);
      } else {
        message.error(result.message);
      }
    } catch (e: any) {
      if (e?.message) message.error(e.message);
    } finally {
      setTesting(false);
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />;

  const providerOptions = Object.entries(config?.providers || {}).map(([value, preset]) => ({
    value, label: preset.label,
  }));
  const keyPlaceholder = config?.configured && config.masked_key
    ? `已保存（${config.masked_key}），留空保持不变`
    : config?.configured
      ? '已保存的密钥无法读取，请重新填写'
      : config?.source === 'env'
        ? '当前使用环境变量中的密钥；填写后将保存到数据库'
        : '请输入 API Key';

  return (
    <div style={{ maxWidth: 780 }}>
      <Title level={3} style={{ marginBottom: 8 }}>AI 设置</Title>
      <Paragraph type="secondary">
        配置大模型服务商，用于「课程表编排」中的 AI 排课分析。未配置时自动使用规则分析，不影响排课流程。
      </Paragraph>

      {config?.enabled === false && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          title="AI 已停用" description="AI 排课分析会使用规则分析；打开「启用 AI」并保存后可调用模型。" />
      )}
      {config?.enabled !== false && config?.source === 'database' && (
        <Alert type="success" showIcon style={{ marginBottom: 16 }}
          title="当前使用数据库中的 AI 配置" description={`服务商：${config?.providers[config.provider]?.label || config.provider}`} />
      )}
      {config?.enabled !== false && config?.source === 'env' && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          title="当前使用环境变量中的 Anthropic 配置"
          description="保存本页配置后，将以数据库配置为准。" />
      )}
      {config?.enabled !== false && config?.source === 'none' && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          title="尚未配置可用的 AI 服务" description="AI 排课分析会使用规则分析；填写并保存密钥后可启用模型分析。" />
      )}
      {config?.configured && !config.masked_key && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          title="已保存的密钥无法解密" description="服务端 SECRET_KEY 可能已更换，请重新填写并保存 API Key。" />
      )}

      <Card>
        <Form form={form} layout="vertical" autoComplete="off">
          <Form.Item name="provider" label="服务商" rules={[{ required: true }]}>
            <Select options={providerOptions} onChange={(value: AIProvider) => {
              const preset = config?.providers?.[value];
              form.setFieldsValue({ base_url: preset?.base_url || '', model: preset?.model || '' });
            }} />
          </Form.Item>
          <Form.Item name="base_url" label="接口地址" rules={[{ required: true, message: '请填写接口地址' }]}>
            <Input placeholder="https://api.deepseek.com" />
          </Form.Item>
          <Form.Item name="model" label="模型名称" rules={[{ required: true, message: '请填写模型名称' }]}>
            <AutoComplete
              options={(provider ? MODEL_SUGGESTIONS[provider] || [] : []).map(value => ({ value }))}
              placeholder="如 deepseek-chat"
            />
          </Form.Item>
          <Form.Item name="api_key" label="API Key"
            extra="密钥仅在服务端加密保存，接口只返回掩码，不会下发到浏览器。">
            <Input.Password placeholder={keyPlaceholder} autoComplete="new-password"
              onChange={e => { if (e.target.value) setClearKey(false); }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用 AI" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
          {config?.configured && (
            <Form.Item>
              <Checkbox checked={clearKey} onChange={e => {
                setClearKey(e.target.checked);
                if (e.target.checked) form.setFieldValue('api_key', '');
              }}>清除已保存的 API Key</Checkbox>
            </Form.Item>
          )}
          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void save()}>
              保存配置
            </Button>
            <Button icon={<ThunderboltOutlined />} loading={testing} onClick={() => void test()}>
              测试连接
            </Button>
          </Space>
        </Form>
      </Card>

      {config?.updated_at && (
        <Space style={{ marginTop: 12 }} size={8}>
          <Tag>最近更新</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {config.updated_by || '—'} · {new Date(config.updated_at).toLocaleString()}
          </Text>
        </Space>
      )}
    </div>
  );
}
