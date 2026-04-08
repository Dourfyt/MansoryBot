import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

async function telegramGetMe(token: string): Promise<{
  username: string;
  id: number;
  first_name: string;
}> {
  const res = await fetch(
    `https://api.telegram.org/bot${encodeURIComponent(token.trim())}/getMe`
  );
  const data = (await res.json()) as {
    ok?: boolean;
    result?: { username?: string; id?: number; first_name?: string };
    description?: string;
  };
  if (!data.ok || !data.result?.username || data.result.id == null) {
    throw new Error(data.description || 'invalid_token');
  }
  const r = data.result;
  return {
    username: r.username!.replace(/^@/, ''),
    id: Number(r.id),
    first_name: (r.first_name || '').trim(),
  };
}

export async function POST(
  request: NextRequest,
  context: { params: { id: string } }
) {
  const denied = await assertAdminOrSupportPermission(request, 'anonymous');
  if (denied) return denied;
  const session = await getSessionFromRequest(request);
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const crmUserId = parseInt(session.sub, 10);
  if (!Number.isFinite(crmUserId)) {
    return NextResponse.json({ error: 'Invalid session' }, { status: 400 });
  }

  const chatId = parseInt(context.params.id, 10);
  if (!Number.isFinite(chatId)) {
    return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
  }

  let body: { token?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Некорректный JSON' }, { status: 400 });
  }
  const token = typeof body.token === 'string' ? body.token.trim() : '';
  if (!token) {
    return NextResponse.json({ error: 'Укажите токен бота' }, { status: 400 });
  }

  let me: { username: string; id: number; first_name: string };
  try {
    me = await telegramGetMe(token);
  } catch {
    return NextResponse.json(
      { error: 'Токен недействителен или Telegram недоступен' },
      { status: 400 }
    );
  }

  const fn = me.first_name || null;

  const { rowCount } = await query(
    `
    UPDATE anonymous_chats
    SET child_bot_token = $1,
        child_bot_username = $2,
        child_bot_id = $3,
        child_bot_first_name = $4
    WHERE id = $5 AND is_active = TRUE
    `,
    [token, me.username, me.id, fn, chatId]
  );
  if (!rowCount) {
    return NextResponse.json({ error: 'Чат не найден или неактивен' }, { status: 404 });
  }

  await appendAudit(crmUserId, 'anonymous_chat_bot_token', `${chatId}`);
  return NextResponse.json({
    ok: true,
    child_bot_username: me.username,
    child_bot_id: me.id,
    child_bot_first_name: me.first_name || null,
  });
}
