export const WEEKDAY_OPTIONS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' },
];

export const WEEKDAY_LABELS: Record<number, string> = Object.fromEntries(
  WEEKDAY_OPTIONS.map(item => [item.value, item.label]));

export function weekdayLabel(days?: number[] | null) {
  return (days || []).map(day => WEEKDAY_LABELS[day]).filter(Boolean).join('、');
}
