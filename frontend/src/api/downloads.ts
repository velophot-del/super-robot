import api from './client';

export type DownloadDataset = 'classes' | 'teachers' | 'courses' | 'classrooms' | 'schedule' | 'all';

export interface DownloadOptions {
  datasets: { key: DownloadDataset; label: string }[];
  plans: { id: number; name: string }[];
  legacy_schedule?: string | null;
}

export const downloadApi = {
  options: () => api.get<unknown, DownloadOptions>('/downloads/options'),
  fetch: (dataset: DownloadDataset, planId?: number) =>
    api.get<Blob>(`/downloads/${dataset}`, {
      params: planId ? { plan_id: planId } : undefined,
      responseType: 'blob',
    }),
};
