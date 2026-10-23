export type CourseFilters = Partial<Record<'department' | 'category' | 'course_type' | 'cohort', string>>;
type Course = {department?: string | null; cohort?: string | null; course_type?: string; course_nature?: string; semester?: number | null};

export type GradeKey = 'freshman' | 'sophomore' | 'junior' | 'senior';
export const GRADE_TABS: { key: GradeKey; label: string; semesters: number[] }[] = [
  { key: 'freshman', label: '大一', semesters: [1, 2] },
  { key: 'sophomore', label: '大二', semesters: [3, 4] },
  { key: 'junior', label: '大三', semesters: [5, 6] },
  { key: 'senior', label: '大四', semesters: [7, 8] },
];

/** 按培养方案学期归属年级页签；未填学期的课程在每个页签保留，五年制及以上归入大四页签。 */
export function inGrade(semester: unknown, key: GradeKey): boolean {
  const value = Number(semester);
  if (!Number.isInteger(value) || value < 1) return true;
  if (value > 8) return key === 'senior';
  return GRADE_TABS.find(tab => tab.key === key)?.semesters.includes(value) ?? true;
}
const parts = (value?: string | null) => (value || '').split(/[,，;；/|]/).map(v => v.trim()).filter(Boolean);
const matches = (value: string | undefined, selected?: string) => !selected || (selected === '__unset__' ? !value : value === selected);

export function filterCourses<T extends Course>(rows: T[], filters: CourseFilters): T[] {
  return rows.filter(row => {
    if (!matches(row.course_type, filters.course_type)) return false;
    const departments = parts(row.department);
    if (filters.department && (filters.department === '__unset__' ? departments.length > 0 : !departments.includes(filters.department))) return false;
    return matches(row.course_nature, filters.category) && matches(row.cohort || undefined, filters.cohort);
  });
}

export function courseFilterOptions(rows: Course[]) {
  const values: Record<keyof CourseFilters, Set<string>> = {
    department: new Set(), category: new Set(), course_type: new Set(), cohort: new Set(),
  };
  for (const row of rows) {
    parts(row.department).forEach(v => values.department.add(v));
    if (row.course_type) values.course_type.add(row.course_type);
    if (row.cohort) values.cohort.add(row.cohort);
    if (row.course_nature) values.category.add(row.course_nature);
  }
  return Object.fromEntries(Object.entries(values).map(([key, list]) => [key, [...list].sort()])) as Record<keyof CourseFilters, string[]>;
}

export async function loadAllCourses(fetchPage: (params: Record<string, unknown>) => Promise<any>, params: Record<string, unknown> = {}) {
  const rows: any[] = [];
  for (let skip = 0; ; skip += 500) {
    const page = await fetchPage({...params, skip, limit: 500});
    rows.push(...page);
    if (page.length < 500) return rows;
  }
}
