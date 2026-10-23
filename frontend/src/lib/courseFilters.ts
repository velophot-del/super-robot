export type CourseFilters = Partial<Record<'department' | 'category' | 'course_type' | 'cohort', string>>;
type Course = {department?: string | null; cohort?: string | null; course_type?: string; course_nature?: string};
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
