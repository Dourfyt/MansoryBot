/**
 * В Mini App initData обычно в window.Telegram.WebApp.initData.
 * При открытии ссылки в обычном браузере или до инжекта TG скрипта
 * те же данные бывают во фрагменте: #tgWebAppData=...&tgWebAppVersion=...
 */
export function getInitDataFromLocationHash(): string | null {
  if (typeof window === 'undefined') return null;
  const raw = window.location.hash;
  if (!raw || raw.length < 2) return null;
  const withoutHash = raw.startsWith('#') ? raw.slice(1) : raw;
  const params = new URLSearchParams(withoutHash);
  const v = params.get('tgWebAppData');
  if (!v?.trim()) return null;
  return v.trim();
}

export function hasTelegramWebContext(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.Telegram?.WebApp) return true;
  return Boolean(getInitDataFromLocationHash());
}
