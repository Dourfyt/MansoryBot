import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { requireSupportOrAdmin, appendAudit } from '@/lib/auth';
import { markSupportTicketRead } from '@/lib/support-ticket-read';

export async function GET(
  request: NextRequest,
  context: { params: { ticketId: string } }
) {
  const session = await requireSupportOrAdmin(request);
  if (!session) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const raw = context.params.ticketId;
  const ticketId = parseInt(raw, 10);
  if (!Number.isFinite(ticketId) || ticketId < 1) {
    return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
  }

  const { rows: trows } = await query<{
    id: number;
    telegram_user_id: string;
    telegram_username: string | null;
    status: string;
    last_message_at: string | null;
    created_at: string | null;
  }>(
    `SELECT id, telegram_user_id, telegram_username, status, last_message_at, created_at
     FROM support_tickets WHERE id = $1`,
    [ticketId]
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
    [ticketId]
  );

  const uid = parseInt(session.sub, 10);
  if (Number.isFinite(uid)) {
    await markSupportTicketRead(uid, ticketId);
  }

  return NextResponse.json({
    ticket: {
      ...ticket,
      telegram_user_id:
        typeof ticket.telegram_user_id === 'string'
          ? Number(ticket.telegram_user_id)
          : ticket.telegram_user_id,
    },
    messages,
  });
}

export async function PATCH(
  request: NextRequest,
  context: { params: { ticketId: string } }
) {
  const session = await requireSupportOrAdmin(request);
  if (!session) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const raw = context.params.ticketId;
  const ticketId = parseInt(raw, 10);
  if (!Number.isFinite(ticketId) || ticketId < 1) {
    return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
  }

  const body = await request.json();
  const action = typeof body.action === 'string' ? body.action.trim() : '';
  if (action !== 'close') {
    return NextResponse.json({ error: 'Ожидается action: close' }, { status: 400 });
  }

  const { rows: exists } = await query<{ id: number }>(
    'SELECT id FROM support_tickets WHERE id = $1',
    [ticketId]
  );
  if (!exists.length) {
    return NextResponse.json({ error: 'Тикет не найден' }, { status: 404 });
  }

  await query(`UPDATE support_tickets SET status = 'closed' WHERE id = $1`, [ticketId]);

  await appendAudit(parseInt(session.sub, 10), 'support_ticket_close', `ticket=${ticketId}`);
  return NextResponse.json({ success: true });
}

export async function DELETE(
  request: NextRequest,
  context: { params: { ticketId: string } }
) {
  const session = await requireSupportOrAdmin(request);
  if (!session) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const raw = context.params.ticketId;
  const ticketId = parseInt(raw, 10);
  if (!Number.isFinite(ticketId) || ticketId < 1) {
    return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
  }

  const { rowCount } = await query('DELETE FROM support_tickets WHERE id = $1', [ticketId]);
  if (!rowCount) {
    return NextResponse.json({ error: 'Тикет не найден' }, { status: 404 });
  }

  await appendAudit(parseInt(session.sub, 10), 'support_ticket_delete', `ticket=${ticketId}`);
  return NextResponse.json({ success: true });
}
