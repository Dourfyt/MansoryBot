import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { resolveBotToken } from '@/lib/resolve-bot-token';
import { parseTelegramUserFromInitData, verifyTelegramWebAppInitData } from '@/lib/telegram-webapp';
import { signTgSupportToken } from '@/lib/tg-support-session';

const BOT_INSTANCE_ID = 1;

export async function POST(request: NextRequest) {
  let body: { initData?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Некорректное тело запроса' }, { status: 400 });
  }

  const initData = typeof body.initData === 'string' ? body.initData.trim() : '';
  if (!initData) {
    return NextResponse.json({ error: 'initData обязателен' }, { status: 400 });
  }

  let botToken: string;
  try {
    botToken = await resolveBotToken();
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Ошибка конфигурации';
    return NextResponse.json({ error: msg }, { status: 500 });
  }

  if (!verifyTelegramWebAppInitData(initData, botToken)) {
    return NextResponse.json({ error: 'Неверная подпись initData' }, { status: 401 });
  }

  const user = parseTelegramUserFromInitData(initData);
  if (!user) {
    return NextResponse.json({ error: 'В initData нет user' }, { status: 400 });
  }

  const telegramUserId = user.id;
  const username = typeof user.username === 'string' ? user.username.trim() || null : null;

  const { rows } = await query<{ id: number }>(
    `
    INSERT INTO support_tickets (bot_instance_id, telegram_user_id, telegram_username, status)
    VALUES ($1, $2, $3, 'open')
    ON CONFLICT (bot_instance_id, telegram_user_id) DO UPDATE SET
      telegram_username = COALESCE(EXCLUDED.telegram_username, support_tickets.telegram_username)
    RETURNING id
    `,
    [BOT_INSTANCE_ID, telegramUserId, username]
  );

  const ticketId = rows[0]?.id;
  if (!ticketId || !Number.isFinite(ticketId)) {
    return NextResponse.json({ error: 'Не удалось создать тикет' }, { status: 500 });
  }

  const token = await signTgSupportToken(telegramUserId, ticketId);
  const res = NextResponse.json({
    ok: true,
    ticketId,
    user: { id: user.id, first_name: user.first_name, username: user.username },
  });
  res.cookies.set('tgSupportToken', token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 30,
  });
  return res;
}
