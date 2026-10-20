export const DEMO_TOKEN_KEY = 'debug_access_token';
export type AuthIdentity = { source: 'demo' | 'normal'; token: string };
type TokenStorage = Pick<Storage, 'getItem' | 'removeItem'>;

export function readAuthIdentity(dev: boolean, normal: TokenStorage, demo: TokenStorage): AuthIdentity | null {
  const demoToken = dev && demo.getItem(DEMO_TOKEN_KEY);
  if (demoToken) return { source: 'demo', token: demoToken };
  const token = normal.getItem('access_token');
  return token ? { source: 'normal', token } : null;
}

export function isCurrentIdentity(identity: AuthIdentity | null, dev: boolean,
  normal: TokenStorage, demo: TokenStorage): boolean {
  const current = readAuthIdentity(dev, normal, demo);
  return Boolean(identity && current && identity.source === current.source && identity.token === current.token);
}

export function clearRejectedIdentity(identity: AuthIdentity | null, dev: boolean,
  normal: TokenStorage, demo: TokenStorage): boolean {
  if (!identity || !isCurrentIdentity(identity, dev, normal, demo)) return false;
  if (identity.source === 'demo') demo.removeItem(DEMO_TOKEN_KEY);
  else normal.removeItem('access_token');
  return true;
}
