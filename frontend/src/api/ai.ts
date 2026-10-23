import api from './client';

export type AIProvider = 'deepseek' | 'qwen' | 'moonshot' | 'zhipu' | 'custom' | 'anthropic';

export interface AIProviderPreset {
  label: string;
  base_url: string;
  model: string;
  protocol: string;
}

export interface AIConfigState {
  provider: AIProvider;
  base_url: string;
  model: string;
  enabled: boolean;
  configured: boolean;
  masked_key: string;
  source: 'database' | 'env' | 'none';
  providers: Record<AIProvider, AIProviderPreset>;
  updated_by?: string | null;
  updated_at?: string | null;
}

export interface AIConfigInput {
  provider: AIProvider;
  base_url: string;
  model: string;
  api_key: string;
  enabled: boolean;
  clear_key?: boolean;
}

export interface AITestResult {
  ok: boolean;
  message: string;
  model?: string;
  latency_ms?: number;
}

export const aiApi = {
  getConfig: () => api.get<unknown, AIConfigState>('/ai/config'),
  saveConfig: (data: AIConfigInput) => api.put<unknown, AIConfigState>('/ai/config', data),
  testConfig: (data: { provider?: AIProvider; base_url?: string; model?: string; api_key?: string }) =>
    api.post<unknown, AITestResult>('/ai/config/test', data),
};
