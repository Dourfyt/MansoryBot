import { query } from './db';

/** Токен из bot_instances (id=1), иначе BOT_TOKEN в окружении — как у процесса бота. */
export async function resolveBotToken(): Promise<string> {
  const { rows } = await query<{ t: string | null }>(
    'SELECT telegram_bot_token AS t FROM bot_instances WHERE id = 1'
  );
  const db = rows[0]?.t?.trim();
  if (db) return db;
  const env = (process.env.BOT_TOKEN || process.env.GROUP_CONNECTOR_BOT_TOKEN || '').trim();
  if (env) return env;
  throw new Error('Токен бота не задан (bot_instances id=1 или BOT_TOKEN)');
}

export async function resolveBotId(): Promise<string> {
  const t = await resolveBotToken();
  return t.split(':')[0] || '';
}

let _usernameCache: { username: string; at: number } | null = null;
const USERNAME_CACHE_MS = 60_000;

/** @username бота для ссылок t.me (env TELEGRAM_BOT_USERNAME или getMe). */
export async function resolveBotUsername(): Promise<string> {
  const env = process.env.TELEGRAM_BOT_USERNAME?.trim();
  if (env) return env.replace(/^@/, '');
  if (_usernameCache && Date.now() - _usernameCache.at < USERNAME_CACHE_MS) {
    return _usernameCache.username;
  }
  const token = await resolveBotToken();
  const res = await fetch(`https://api.telegram.org/bot${encodeURIComponent(token)}/getMe`);
  const data = (await res.json()) as { ok?: boolean; result?: { username?: string } };
  const u = data.result?.username;
  if (!data.ok || !u) {
    throw new Error('Не удалось получить username бота (getMe)');
  }
  _usernameCache = { username: u, at: Date.now() };
  return u;
}
