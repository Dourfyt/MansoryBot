import { query } from '@/lib/db';
import { resolveBotToken } from '@/lib/resolve-bot-token';

/** Уведомления в Telegram всем support с заполненным telegram_user_id. */
export async function notifySupportStaffNewTicketMessage(
  ticketId: number,
  bodyPreview: string
): Promise<void> {
  let token: string;
  try {
    token = await resolveBotToken();
  } catch {
    return;
  }

  const { rows } = await query<{ telegram_user_id: string | null }>(
    `SELECT telegram_user_id::text AS telegram_user_id FROM crm_users
     WHERE role = 'support' AND telegram_user_id IS NOT NULL`
  );

  const ids = new Set<number>();
  for (const r of rows) {
    if (r.telegram_user_id == null) continue;
    const n = parseInt(String(r.telegram_user_id), 10);
    if (Number.isFinite(n) && n > 0) ids.add(n);
  }
  if (ids.size === 0) return;

  const preview = (bodyPreview || '').trim().slice(0, 400);
  const text = `💬 Новое сообщение в тикете #${ticketId}\n\n${preview || '—'}`;

  for (const chatId of ids) {
    try {
      await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          text,
          disable_web_page_preview: true,
        }),
      });
    } catch {
      /* ignore */
    }
  }
}
