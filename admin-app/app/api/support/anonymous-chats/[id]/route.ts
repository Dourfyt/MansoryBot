import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';
import { assertAnonymousChatsApi } from '@/lib/api-guard';

export async function PATCH(
  request: NextRequest,
  context: { params: { id: string } }
) {
  const denied = await assertAnonymousChatsApi(request);
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

  let body: { verifier_group_id?: number | null };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Некорректный JSON' }, { status: 400 });
  }

  const raw = body.verifier_group_id;
  if (raw === undefined) {
    return NextResponse.json({ error: 'Укажите verifier_group_id' }, { status: 400 });
  }
  let sqlVal: number | null;
  if (raw === null) {
    sqlVal = null;
  } else {
    const n = typeof raw === 'number' ? raw : parseInt(String(raw), 10);
    if (!Number.isFinite(n) || n === 0) {
      return NextResponse.json(
        { error: 'Укажите ID группы Telegram (для супергруппы — отрицательное число) или null' },
        { status: 400 }
      );
    }
    sqlVal = n;
  }

  const { rows } = await query<{ id: number }>(
    'UPDATE anonymous_chats SET verifier_group_id = $1 WHERE id = $2 RETURNING id',
    [sqlVal, chatId]
  );
  if (!rows.length) {
    return NextResponse.json({ error: 'Чат не найден' }, { status: 404 });
  }

  await appendAudit(crmUserId, 'anonymous_chat_verifier_group', String(chatId));
  return NextResponse.json({ ok: true });
}

export async function DELETE(
  request: NextRequest,
  context: { params: { id: string } }
) {
  const denied = await assertAnonymousChatsApi(request);
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

  const { rowCount } = await query('DELETE FROM anonymous_chats WHERE id = $1', [chatId]);
  if (!rowCount) {
    return NextResponse.json({ error: 'Чат не найден' }, { status: 404 });
  }

  await appendAudit(crmUserId, 'anonymous_chat_delete', String(chatId));
  return NextResponse.json({ ok: true });
}
