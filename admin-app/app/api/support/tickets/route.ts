import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { requireSupportOrAdmin, appendAudit } from '@/lib/auth';
import { resolveBotToken } from '@/lib/resolve-bot-token';

export async function GET(request: NextRequest) {
  const session = await requireSupportOrAdmin(request);
  if (!session) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const crmUserId = parseInt(session.sub, 10);
  if (!Number.isFinite(crmUserId)) {
    return NextResponse.json({ error: 'Invalid session' }, { status: 400 });
  }

  const { rows } = await query<{
    id: number;
    telegram_user_id: string;
    telegram_username: string | null;
    status: string;
    last_message_at: string | null;
    last_body: string | null;
    unread_count: string;
  }>(`
    SELECT t.id, t.telegram_user_id, t.telegram_username, t.status, t.last_message_at,
      (SELECT body FROM support_messages m WHERE m.ticket_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_body,
      COALESCE((
        SELECT COUNT(*)::int FROM support_messages m
        WHERE m.ticket_id = t.id AND m.direction = 'in'
          AND m.id > COALESCE(
            (SELECT r.last_read_message_id FROM support_ticket_reads r
             WHERE r.crm_user_id = $1 AND r.ticket_id = t.id),
            0
          )
      ), 0)::text AS unread_count
    FROM support_tickets t
    ORDER BY COALESCE(t.last_message_at, t.created_at) DESC NULLS LAST
    LIMIT 300
  `, [crmUserId]);
  return NextResponse.json({
    tickets: rows.map((r) => ({
      ...r,
      telegram_user_id: typeof r.telegram_user_id === 'string' ? Number(r.telegram_user_id) : r.telegram_user_id,
      unread_count: parseInt(r.unread_count, 10) || 0,
    })),
  });
}

export async function POST(request: NextRequest) {
  const session = await requireSupportOrAdmin(request);
  if (!session) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const body = await request.json();
  const ticketId = typeof body.ticket_id === 'number' ? body.ticket_id : parseInt(String(body.ticket_id), 10);
  const text = typeof body.text === 'string' ? body.text.trim() : '';
  if (!ticketId || !text) {
    return NextResponse.json({ error: 'Нужны ticket_id и text' }, { status: 400 });
  }

  let token: string;
  try {
    token = await resolveBotToken();
  } catch {
    return NextResponse.json({ error: 'BOT_TOKEN не задан' }, { status: 500 });
  }

  const { rows } = await query<{ telegram_user_id: string }>(
    'SELECT telegram_user_id FROM support_tickets WHERE id = $1',
    [ticketId]
  );
  const row = rows[0];
  if (!row) {
    return NextResponse.json({ error: 'Тикет не найден' }, { status: 404 });
  }

  const prefix = '💬 Сообщение от поддержки:\n\n';
  const maxBody = 4096 - prefix.length;
  const safe =
    text.length > maxBody ? `${text.slice(0, Math.max(0, maxBody - 3))}...` : text;
  const outgoing = `${prefix}${safe}`;

  const chatId = Number(row.telegram_user_id);
  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      text: outgoing,
      disable_web_page_preview: true,
    }),
  });
  const data = await res.json();
  if (!data.ok) {
    return NextResponse.json({ error: data.description || 'Telegram API error' }, { status: 502 });
  }

  await query('INSERT INTO support_messages (ticket_id, direction, body) VALUES ($1, $2, $3)', [
    ticketId,
    'out',
    text,
  ]);
  await query(
    `UPDATE support_tickets SET last_message_at = CURRENT_TIMESTAMP, status = 'open' WHERE id = $1`,
    [ticketId]
  );

  await appendAudit(parseInt(session.sub, 10), 'support_reply', `ticket=${ticketId}`);
  return NextResponse.json({ success: true });
}
