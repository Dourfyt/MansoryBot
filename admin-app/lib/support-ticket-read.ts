import { query } from '@/lib/db';

/** Отмечает тикет прочитанным до последнего сообщения (все входящие до этого id считаются просмотренными). */
export async function markSupportTicketRead(crmUserId: number, ticketId: number): Promise<void> {
  await query(
    `
    INSERT INTO support_ticket_reads (crm_user_id, ticket_id, last_read_message_id, updated_at)
    VALUES (
      $1,
      $2,
      (SELECT COALESCE(MAX(id), 0) FROM support_messages WHERE ticket_id = $2),
      NOW()
    )
    ON CONFLICT (crm_user_id, ticket_id) DO UPDATE SET
      last_read_message_id = EXCLUDED.last_read_message_id,
      updated_at = NOW()
    `,
    [crmUserId, ticketId]
  );
}
