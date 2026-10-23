import type { UserInfo } from '../types';

export function can(user: UserInfo | null | undefined, action: string): boolean {
  return Boolean(user?.grants?.some(g => g.capability === action || (action === 'review' && g.capability === 'lead')));
}

// 旧接口兼容函数仅供已存在的回归测试；实际业务入口使用can职能判断。
export function canManage(role?: string): boolean {
  return role !== 'teacher';
}

export function navigationKeys(role?: string): string[] {
  return canManage(role) ? ['/', 'data', 'schedule', '/timetable', '/export'] : ['/timetable'];
}

export function requiresAccountSetup(user: UserInfo | null | undefined): boolean {
  return Boolean(user && (user.password_change_required || user.profile_required));
}
