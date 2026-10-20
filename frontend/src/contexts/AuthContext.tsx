// 认证上下文 — 管理全局登录状态
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { authApi, debugApi, DEMO_TOKEN_KEY } from '../api/client';
import type { UserInfo, LoginRequest, RegisterRequest } from '../types';
import { readAuthIdentity, isCurrentIdentity } from '../api/authSession';

interface AuthState {
  user: UserInfo | null;
  token: string | null;
  loading: boolean;
  demoEnabled: boolean;
  switchDemo: (role: 'admin' | 'teacher', teacherId?: number) => Promise<void>;
  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('access_token'));
  const [loading, setLoading] = useState(true);
  const [demoEnabled, setDemoEnabled] = useState(false);

  // 应用启动时，尝试用本地 token 获取用户信息
  useEffect(() => {
    let active = true;
    const bootstrap = async () => {
      let enabled = false;
      if (import.meta.env.DEV) {
        try { enabled = (await debugApi.status()).enabled; } catch { /* 正常登录仍可使用 */ }
      }
      if (!active) return;
      setDemoEnabled(enabled);
      if (!enabled) sessionStorage.removeItem(DEMO_TOKEN_KEY);
      const identity = readAuthIdentity(import.meta.env.DEV, localStorage, sessionStorage);
      setToken(identity?.token || null);
      if (identity) {
        try {
          const current: any = await authApi.getMe();
          if (active && isCurrentIdentity(identity, import.meta.env.DEV, localStorage, sessionStorage)) setUser(current);
        } catch {
          if (active && !readAuthIdentity(import.meta.env.DEV, localStorage, sessionStorage)) {
            setToken(null); setUser(null);
          }
        }
      }
      if (active) setLoading(false);
    };
    void bootstrap();
    return () => { active = false; };
  }, []); // 仅在挂载时执行一次

  const login = useCallback(async (data: LoginRequest) => {
    const res: any = await authApi.login(data);
    sessionStorage.removeItem(DEMO_TOKEN_KEY);
    localStorage.setItem('access_token', res.access_token);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const register = useCallback(async (data: RegisterRequest) => {
    const res: any = await authApi.register(data);
    sessionStorage.removeItem(DEMO_TOKEN_KEY);
    localStorage.setItem('access_token', res.access_token);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    if (user?.is_demo) sessionStorage.removeItem(DEMO_TOKEN_KEY);
    else localStorage.removeItem('access_token');
    setToken(null);
    setUser(null);
  }, [user]);

  const switchDemo = useCallback(async (role: 'admin' | 'teacher', teacherId?: number) => {
    if (!demoEnabled) throw new Error('演示模式未启用');
    const res = await debugApi.session(role, teacherId);
    sessionStorage.setItem(DEMO_TOKEN_KEY, res.access_token);
    window.location.assign('/planning');
  }, [demoEnabled]);

  return (
    <AuthContext.Provider value={{ user, token, loading, demoEnabled, switchDemo, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth 必须在 AuthProvider 内部使用');
  }
  return ctx;
}
