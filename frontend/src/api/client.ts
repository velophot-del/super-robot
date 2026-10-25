// API 客户端配置
import axios from 'axios';
import { errorMessage } from './errorMessage';
import type { AxiosInstance, AxiosRequestConfig } from 'axios';
type DataClient = Omit<AxiosInstance, 'get' | 'post' | 'put' | 'delete'> & {
  get<T = any, R = T>(url: string, config?: AxiosRequestConfig): Promise<R>;
  post<T = any, R = T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<R>;
  put<T = any, R = T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<R>;
  delete<T = any, R = T>(url: string, config?: AxiosRequestConfig): Promise<R>;
};
import type { TokenResponse } from '../types';
import { readAuthIdentity, clearRejectedIdentity } from './authSession';
import type { AuthIdentity } from './authSession';
export { DEMO_TOKEN_KEY } from './authSession';

const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
}) as DataClient;

// 请求拦截器 — 自动携带 JWT Token
apiClient.interceptors.request.use(
  (config) => {
    const identity = readAuthIdentity(import.meta.env.DEV, localStorage, sessionStorage);
    Object.assign(config, { authIdentity: identity });
    if (identity) {
      config.headers.Authorization = `Bearer ${identity.token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    // 401 未认证，清除 token 并跳转登录页
    if (error.response?.status === 401) {
      const identity = error.config?.authIdentity as AuthIdentity | null;
      const cleared = clearRejectedIdentity(identity, import.meta.env.DEV, localStorage, sessionStorage);
      if (identity?.source === 'demo') {
        if (cleared && window.location.pathname !== '/debug') window.location.href = '/debug';
        return Promise.reject(new Error('演示身份已失效，请重新选择'));
      }
      if (cleared && !['/login', '/register', '/debug'].includes(window.location.pathname)) {
        window.location.href = '/login';
      }
    }

    let message = error.message || '请求失败';
    const respData = error.response?.data;

    if (respData) {
      if (respData instanceof Blob) {
        // Blob 类型响应（导出 API 等），读取文本提取后端错误详情
        try {
          const text = await respData.text();
          const parsed = JSON.parse(text);
          message = errorMessage(parsed.detail,message);
        } catch {
          // 无法解析则使用默认错误消息
        }
      } else if (typeof respData === 'object' && respData.detail) {
        // FastAPI JSON 错误响应 {"detail": "..."}
        message = errorMessage(respData.detail,message);
      } else if (typeof respData === 'string' && respData.length > 0 && respData.length < 200) {
        // 纯文本错误响应（如 "Internal Server Error"）
        message = respData;
      }
    }

    console.error('API Error:', message);
    return Promise.reject(new Error(message));
  }
);

export default apiClient;

export interface DemoTeacher { id: number; name: string; teacher_code: string }
export const debugApi = {
  status: () => apiClient.get<unknown, { enabled: boolean }>('/debug/status'),
  identities: () => apiClient.get<unknown, { teachers: DemoTeacher[] }>('/debug/identities'),
  session: (role: 'admin' | 'teacher', teacher_id?: number) =>
    apiClient.post<unknown, TokenResponse>('/debug/session', { role, teacher_id }),
};

// ===== 班级 API =====
export const classApi = {
  list: (params?: any) => apiClient.get('/classes/', { params }),
  get: (id: number) => apiClient.get(`/classes/${id}`),
  create: (data: any) => apiClient.post('/classes/', data),
  update: (id: number, data: any) => apiClient.put(`/classes/${id}`, data),
  delete: (id: number) => apiClient.delete(`/classes/${id}`),
  getCourses: (id: number, version?: string) =>
    apiClient.get(`/classes/${id}/courses`, { params: { version } }),
};

// ===== 教师 API =====
export const teacherApi = {
  list: (params?: any) => apiClient.get('/teachers/', { params }),
  get: (id: number) => apiClient.get(`/teachers/${id}`),
  create: (data: any) => apiClient.post('/teachers/', data),
  update: (id: number, data: any) => apiClient.put(`/teachers/${id}`, data),
  delete: (id: number) => apiClient.delete(`/teachers/${id}`),
  getCourses: (id: number, version?: string) =>
    apiClient.get(`/teachers/${id}/courses`, { params: { version } }),
  getCourseAffiliations: (id: number) => apiClient.get(`/teachers/${id}/course-affiliations`),
};

// ===== 课程 API =====
export const courseApi = {
  list: (params?: any) => apiClient.get('/courses/', { params }),
  get: (id: number) => apiClient.get(`/courses/${id}`),
  create: (data: any) => apiClient.post('/courses/', data),
  update: (id: number, data: any) => apiClient.put(`/courses/${id}`, data),
  delete: (id: number) => apiClient.delete(`/courses/${id}`),
  bulkUpdate: (ids: number[], updates: Record<string, unknown>) => apiClient.patch('/courses/bulk', { ids, updates }),
  bulkRemove: (ids: number[]) => apiClient.delete('/courses/bulk', { data: { ids } }),
};

// ===== 教室 API =====
export const classroomApi = {
  list: (params?: any) => apiClient.get('/classrooms/', { params }),
  get: (id: number) => apiClient.get(`/classrooms/${id}`),
  create: (data: any) => apiClient.post('/classrooms/', data),
  update: (id: number, data: any) => apiClient.put(`/classrooms/${id}`, data),
  delete: (id: number) => apiClient.delete(`/classrooms/${id}`),
};

// ===== 排课 API =====
export const scheduleApi = {
  myList: (params?: { limit?: number; version?: string }) => apiClient.get('/my/timetable', { params }),
  generate: (data: any) => apiClient.post('/schedules/generate', data),
  list: (params?: any) => apiClient.get('/schedules/', { params }),
  update: (id: number, data: any) => apiClient.put(`/schedules/${id}`, data),
  delete: (id: number) => apiClient.delete(`/schedules/${id}`),
  deleteVersion: (version: string) => apiClient.delete(`/schedules/version/${version}`),
  getVersions: () => apiClient.get('/schedules/versions'),
  getConflicts: (version?: string) => apiClient.get('/schedules/conflicts', { params: { version } }),
  getExplanation: (version?: string) => apiClient.get('/schedules/explanation', { params: { version } }),
};

// ===== 导入导出 API =====
export const ioApi = {
  downloadTemplate: (entityType: string) =>
    apiClient.get(`/io/template/${entityType}`, { responseType: 'blob' }),
  importCsv: (entityType: string, file: File, cohort?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (cohort) formData.append('cohort', cohort);
    return apiClient.post(`/io/csv/${entityType}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  previewCoursesXlsx: (file:File, cohort?: string) => {const form=new FormData();form.append('file',file);if(cohort)form.append('cohort',cohort);return apiClient.post('/io/xlsx/courses/preview',form,{headers:{'Content-Type':'multipart/form-data'}});},
  confirmCoursesXlsx: (preview_id:number,token:string) => apiClient.post('/io/xlsx/courses/confirm',{preview_id,token}),
  downloadCoursesXlsxTemplate: () => apiClient.get('/io/template/courses/xlsx',{responseType:'blob'}),
  previewAcademicCatalogXlsx: (file:File) => {const form=new FormData();form.append('file',file);return apiClient.post('/io/xlsx/academic-catalog/preview',form,{headers:{'Content-Type':'multipart/form-data'}});},
  confirmAcademicCatalogXlsx: (preview_id:number,token:string) => apiClient.post('/io/xlsx/academic-catalog/confirm',{preview_id,token}),
  downloadAcademicCatalogXlsxTemplate: () => apiClient.get('/io/xlsx/academic-catalog/template',{responseType:'blob'}),
  exportExcel: (version?: string) =>
    apiClient.get('/io/export/excel', { params: { version }, responseType: 'blob' }),
  exportPdf: (version?: string, viewType?: string) =>
    apiClient.get('/io/export/pdf', { params: { version, view_type: viewType }, responseType: 'blob' }),
  getReport: (version?: string) => apiClient.get('/io/report', { params: { version } }),
};

// ===== 认证 API =====
export const authApi = {
  register: (data: { username: string; email: string; password: string }) =>
    apiClient.post('/auth/register', data),
  login: (data: { username: string; password: string }) =>
    apiClient.post('/auth/login', data),
  getMe: () => apiClient.get('/auth/me'),
  changePassword: (data: {current_password: string; new_password: string}) => apiClient.post('/auth/password', data),
};

// ===== AI 智能辅助 API =====
export const intelligenceApi = {
  reviewImport: (entityType: 'course' | 'teacher', records: unknown[]) =>
    apiClient.post('/intelligence/import/review', { entity_type: entityType, records }),
  reviewImportFile: (entityType: 'course' | 'teacher', file: File) => {
    const form = new FormData();
    form.append('entity_type', entityType);
    form.append('file', file);
    return apiClient.post('/intelligence/import/review-file', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  qa: (question: string) => apiClient.post('/intelligence/qa', { question }),
  myQa: (question: string) => apiClient.post('/intelligence/my-qa', { question }),
  recommend: (planId: number) => apiClient.get(`/intelligence/plans/${planId}/recommend`),
};
