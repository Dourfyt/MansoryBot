import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';
import { assertAnonymousChatsApi } from '@/lib/api-guard';
import { anonymousChatsEmptyGetResponse } from '@/lib/anonymous-chats-feature';

const LABEL_RE = /^[A-Z]$/;

function supportDisplayNickname(label: string): string {
  return `👁‍🗨 Саппорт ${label}`;
}

export async function GET(
  request: NextRequest,
  context: { params: { id: string } }
) {
  const empty = anonymousChatsEmptyGetResponse({ assigned: [], support_users: [] });
  if (empty) return empty;
  const denied = await assertAnonymousChatsApi(request);
  if (denied) return denied;

  const chatId = parseInt(context.params.id, 10);
  if (!Number.isFinite(chatId)) {
    return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
  }

  const { rows: assigned } = await query<{
    crm_user_id: number;
    label: string;
    email: string;
    telegram_user_id: string | null;
  }>(
    `
    SELECT acsa.crm_user_id, acsa.label, u.email, u.telegram_user_id::text AS telegram_user_id
    FROM anonymous_chat_support_admins acsa
    INNER JOIN crm_users u ON u.id = acsa.crm_user_id
    WHERE acsa.anonymous_chat_id = $1
    ORDER BY acsa.label
    `,
    [chatId]
  );

  const { rows: supportUsers } = await query<{
    id: number;
    email: string;
    telegram_user_id: string | null;
  }>(
    `
    SELECT id, email, telegram_user_id::text AS telegram_user_id
    FROM crm_users
    WHERE role = 'support'
    ORDER BY email
    `
  );

  return NextResponse.json({
    assigned,
    support_users: supportUsers,
  });
}

export async function POST(
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

  let body: { crm_user_id?: number; label?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Некорректный JSON' }, { status: 400 });
  }

  const targetCrm = typeof body.crm_user_id === 'number' ? body.crm_user_id : parseInt(String(body.crm_user_id), 10);
  const label = typeof body.label === 'string' ? body.label.trim().toUpperCase() : '';
  if (!Number.isFinite(targetCrm) || !LABEL_RE.test(label)) {
    return NextResponse.json(
      { error: 'Укажите crm_user_id (саппорт) и label — одна латинская буква A–Z' },
      { status: 400 }
    );
  }

  const { rows: roleRows } = await query<{ role: string }>(
    `SELECT role FROM crm_users WHERE id = $1`,
    [targetCrm]
  );
  if (!roleRows.length || roleRows[0].role !== 'support') {
    return NextResponse.json({ error: 'Пользователь не найден или не саппорт' }, { status: 400 });
  }

  const { rows: tgRows } = await query<{ telegram_user_id: string | null }>(
    `SELECT telegram_user_id::text AS telegram_user_id FROM crm_users WHERE id = $1`,
    [targetCrm]
  );
  if (!tgRows[0]?.telegram_user_id) {
    return NextResponse.json(
      { error: 'У саппорта не привязан Telegram user id в CRM (нужен для бота)' },
      { status: 400 }
    );
  }

  try {
    await query(
      `
      INSERT INTO anonymous_chat_support_admins (anonymous_chat_id, crm_user_id, label)
      VALUES ($1, $2, $3)
      `,
      [chatId, targetCrm, label]
    );
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/unique|duplicate/i.test(msg)) {
      return NextResponse.json(
        { error: 'Этот саппорт или буква уже назначены на комнату' },
        { status: 409 }
      );
    }
    throw e;
  }

  await query(
    `
    UPDATE anonymous_chat_members m
    SET nickname = $1
    FROM crm_users u
    WHERE m.telegram_user_id = u.telegram_user_id
      AND m.anonymous_chat_id = $2
      AND u.id = $3
    `,
    [supportDisplayNickname(label), chatId, targetCrm]
  );

  await appendAudit(crmUserId, 'anonymous_chat_support_admin', `${chatId}:${targetCrm}:${label}`);
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

  const url = new URL(request.url);
  const removeId = parseInt(url.searchParams.get('crm_user_id') || '', 10);
  if (!Number.isFinite(removeId)) {
    return NextResponse.json({ error: 'Укажите crm_user_id (query)' }, { status: 400 });
  }

  const { rowCount } = await query(
    `DELETE FROM anonymous_chat_support_admins WHERE anonymous_chat_id = $1 AND crm_user_id = $2`,
    [chatId, removeId]
  );
  if (!rowCount) {
    return NextResponse.json({ error: 'Назначение не найдено' }, { status: 404 });
  }

  await appendAudit(crmUserId, 'anonymous_chat_support_admin_remove', `${chatId}:${removeId}`);
  return NextResponse.json({ ok: true });
}
