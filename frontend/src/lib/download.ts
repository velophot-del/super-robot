import { downloadApi } from '../api/downloads';
import type { DownloadDataset } from '../api/downloads';

export const DATASET_LABELS: Record<DownloadDataset, string> = {
  classes: '班级数据',
  teachers: '教师数据',
  courses: '课程数据',
  classrooms: '教室数据',
  schedule: '课表数据',
  all: '全部数据',
};

export async function downloadDataset(dataset: DownloadDataset, planId?: number) {
  const blob = await downloadApi.fetch(dataset, planId);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${DATASET_LABELS[dataset]}_${new Date().toISOString().slice(0, 10)}.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
