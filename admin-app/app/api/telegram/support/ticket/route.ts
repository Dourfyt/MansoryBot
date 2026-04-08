import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { notifySupportStaffNewTicketMessage } from '@/lib/notify-support-staff';
import { assertSupportIncomingAllowed } from '@/lib/tg-support-rate-limit';
import { verifyTgSupportToken } from '@/lib/tg-support-session';

async function getSession(request: NextRequest) {
  const token = request.cookies.get('tgSupportToken')?.value;
  if (!token) return null;
  const payload = await verifyTgSupportToken(token);
  if (!payload) return null;
  const tgId = parseInt(payload.sub, 10);
  if (!Number.isFinite(tgId)) return null;
  return { ...payload, telegramUserId: tgId };
}

export async function GET(request: NextRequest) {
  const session = await getSession(request);
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { rows: trows } = await query<{
    id: number;
    telegram_user_id: string;
    status: string;
    last_message_at: string | null;
  }>(
    `SELECT id, telegram_user_id::text, status, last_message_at
     FROM support_tickets
     WHERE id = $1 AND telegram_user_id = $2`,
    [session.tid, session.telegramUserId]
  );
  const ticket = trows[0];
  if (!ticket) {
    return NextResponse.json({ error: 'Тикет не найден' }, { status: 404 });
  }

  const { rows: messages } = await query<{
    id: number;
    direction: string;
    body: string | null;
    created_at: string | null;
  }>(
    `SELECT id, direction, body, created_at
     FROM support_messages WHERE ticket_id = $1
     ORDER BY id ASC`,
    [session.tid]
  );

  return NextResponse.json({
    ticket: {
      id: ticket.id,
      status: ticket.status,
      last_message_at: ticket.last_message_at,
    },
    messages,
  });
}

export async function POST(request: NextRequest) {
  const session = await getSession(request);
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: { text?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Некорректное тело запроса' }, { status: 400 });
  }

  const text = typeof body.text === 'string' ? body.text.trim() : '';
  if (!text) {
    return NextResponse.json({ error: 'Пустое сообщение' }, { status: 400 });
  }
  if (text.length > 10000) {
    return NextResponse.json({ error: 'Слишком длинное сообщение' }, { status: 400 });
  }

  const { rows: trows } = await query<{ id: number; status: string }>(
    `SELECT id, status FROM support_tickets WHERE id = $1 AND telegram_user_id = $2`,
    [session.tid, session.telegramUserId]
  );
  const row = trows[0];
  if (!row) {
    return NextResponse.json({ error: 'Тикет не найден' }, { status: 404 });
  }

  try {
    await assertSupportIncomingAllowed(session.tid);
  } catch (e) {
    const code = e instanceof Error ? e.message : '';
    if (code === 'too_fast') {
      return NextResponse.json({ error: 'Подождите несколько секунд перед следующим сообщением' }, { status: 429 });
    }
    if (code === 'too_many_per_minute') {
      return NextResponse.json({ error: 'Слишком много сообщений в минуту' }, { status: 429 });
    }
    throw e;
  }

  await query(
    `INSERT INTO support_messages (ticket_id, direction, body) VALUES ($1, 'in', $2)`,
    [session.tid, text]
  );

  await query(
    `UPDATE support_tickets
     SET last_message_at = CURRENT_TIMESTAMP,
         status = CASE WHEN status = 'closed' THEN 'open' ELSE status END
     WHERE id = $1`,
    [session.tid]
  );

  await notifySupportStaffNewTicketMessage(session.tid, text);

  return NextResponse.json({ ok: true });
}
