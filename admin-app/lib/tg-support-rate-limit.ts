import { query } from '@/lib/db';

const MIN_INTERVAL_SEC = Number(process.env.SUPPORT_MIN_INTERVAL_SEC ?? '4') || 4;
const MAX_IN_PER_MINUTE = Number(process.env.SUPPORT_MAX_MSG_PER_MINUTE ?? '18') || 18;

export async function assertSupportIncomingAllowed(ticketId: number): Promise<void> {
  const { rows: cnt } = await query<{ c: string }>(
    `
    SELECT COUNT(*)::text AS c FROM support_messages
    WHERE ticket_id = $1 AND direction = 'in'
      AND created_at > NOW() - INTERVAL '1 minute'
    `,
    [ticketId]
  );
  const n = parseInt(cnt[0]?.c ?? '0', 10);
  if (n >= MAX_IN_PER_MINUTE) {
    throw new Error('too_many_per_minute');
  }

  const { rows: last } = await query<{ sec: string | null }>(
    `
    SELECT EXTRACT(EPOCH FROM (NOW() - created_at))::text AS sec
    FROM support_messages
    WHERE ticket_id = $1 AND direction = 'in'
    ORDER BY id DESC LIMIT 1
    `,
    [ticketId]
  );
  const sec = last[0]?.sec != null ? parseFloat(last[0].sec) : null;
  if (sec != null && Number.isFinite(sec) && sec < MIN_INTERVAL_SEC) {
    throw new Error('too_fast');
  }
}
