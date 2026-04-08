import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { requireSupportOrAdmin } from '@/lib/auth';

export async function GET(request: NextRequest) {
  const session = await requireSupportOrAdmin(request);
  if (!session) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const crmUserId = parseInt(session.sub, 10);
  if (!Number.isFinite(crmUserId)) {
    return NextResponse.json({ error: 'Invalid session' }, { status: 400 });
  }

  const { rows } = await query<{ total: string }>(
    `
    SELECT COALESCE(SUM(
      (
        SELECT COUNT(*)::bigint FROM support_messages m
        WHERE m.ticket_id = t.id AND m.direction = 'in'
          AND m.id > COALESCE(
            (SELECT r.last_read_message_id FROM support_ticket_reads r
             WHERE r.crm_user_id = $1 AND r.ticket_id = t.id),
            0
          )
      )
    ), 0)::text AS total
    FROM support_tickets t
    `,
    [crmUserId]
  );

  const total = parseInt(rows[0]?.total ?? '0', 10) || 0;
  return NextResponse.json({ total });
}
