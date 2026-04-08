import crypto from 'crypto';

/** Проверка подписи initData из Telegram Mini App (см. core.telegram.org/bots/webapps). */
export function verifyTelegramWebAppInitData(initData: string, botToken: string): boolean {
  const params = new URLSearchParams(initData);
  const hash = params.get('hash');
  if (!hash) return false;
  params.delete('hash');

  const authDate = params.get('auth_date');
  if (authDate) {
    const ts = parseInt(authDate, 10);
    if (!Number.isFinite(ts)) return false;
    const ageSec = Math.abs(Date.now() / 1000 - ts);
    if (ageSec > 86400) return false;
  }

  const dataCheckString = Array.from(params.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join('\n');

  const secretKey = crypto.createHmac('sha256', 'WebAppData').update(botToken).digest();
  const calculatedHash = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');
  return calculatedHash === hash;
}

export interface TelegramWebAppUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

export function parseTelegramUserFromInitData(initData: string): TelegramWebAppUser | null {
  const params = new URLSearchParams(initData);
  const raw = params.get('user');
  if (!raw) return null;
  try {
    const u = JSON.parse(raw) as TelegramWebAppUser;
    if (typeof u.id !== 'number' || !Number.isFinite(u.id)) return null;
    return u;
  } catch {
    return null;
  }
}
