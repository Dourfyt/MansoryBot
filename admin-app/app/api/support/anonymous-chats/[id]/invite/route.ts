import { NextRequest, NextResponse } from 'next/server';
import crypto from 'crypto';
import { query } from '@/lib/db';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';
import { resolveBotUsername } from '@/lib/resolve-bot-token';

const INVITE_TTL_MINUTES = 180;

const INVITE_USER_MESSAGE =
  '🤖 Ссылка-приглашение активна 180 минут и позволяет одному пользователю подключиться к этому чату\n\n';

function generateInviteToken(): string {
  return crypto
    .randomBytes(12)
    .toString('base64url')
    .replace(/\+/g, 'x')
    .replace(/\//g, 'y')
    .slice(0, 32);
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

  const { rows: exists } = await query<{ id: number; child_bot_username: string | null }>(
    `SELECT id, NULLIF(TRIM(child_bot_username), '') AS child_bot_username
     FROM anonymous_chats WHERE id = $1 AND is_active = TRUE`,
    [chatId]
  );
  if (!exists.length) {
    return NextResponse.json({ error: 'Чат не найден' }, { status: 404 });
  }
  const childUsername = exists[0]?.child_bot_username?.trim();

  const token = generateInviteToken();
  const expiresAt = new Date(Date.now() + INVITE_TTL_MINUTES * 60 * 1000);
  const { rows } = await query<{ token: string; expires_at: string }>(
    `INSERT INTO anonymous_chat_invites (anonymous_chat_id, token, expires_at)
     VALUES ($1, $2, $3)
     RETURNING token, expires_at`,
    [chatId, token, expiresAt.toISOString()]
  );
  const row = rows[0];
  if (!row) {
    return NextResponse.json({ error: 'Не удалось создать приглашение' }, { status: 500 });
  }

  let username: string;
  if (childUsername) {
    username = childUsername.replace(/^@/, '');
  } else {
    try {
      username = await resolveBotUsername();
    } catch {
      return NextResponse.json(
        { error: 'Задайте TELEGRAM_BOT_USERNAME или проверьте токен бота' },
        { status: 500 }
      );
    }
  }

  const inviteUrl = `https://t.me/${username}?start=${encodeURIComponent(row.token)}`;
  const invite_text = INVITE_USER_MESSAGE + inviteUrl;

  await appendAudit(crmUserId, 'anonymous_chat_invite', `${chatId}`);

  return NextResponse.json({
    token: row.token,
    expires_at: row.expires_at,
    invite_url: inviteUrl,
    invite_text,
  });
}
