export function errorMessage(detail: unknown, fallback='请求失败'): string {
  if (typeof detail==='string') return detail || fallback;
  if (Array.isArray(detail)) return detail.map(item=>errorMessage(item,fallback)).join('；');
  if (detail && typeof detail==='object') {
    const item=detail as {msg?:unknown;loc?:unknown;detail?:unknown};
    if (typeof item.msg==='string') return `${Array.isArray(item.loc)?item.loc.filter(x=>x!=='body').join('.')+': ':''}${item.msg}`;
    if (item.detail!==undefined) return errorMessage(item.detail,fallback);
  }
  return fallback;
}
