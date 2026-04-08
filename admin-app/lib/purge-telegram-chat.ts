import type { PoolClient } from 'pg';
import { withTransaction } from '@/lib/db';

/**
 * Полное удаление данных группы по Telegram chat_id:
 * чеки, настройки, участие в рассылке, связи connections (деактивация),
 * чтобы ежедневная и ручная рассылка больше не шли в этот чат.
 */
export async function purgeTelegramChat(chatId: number): Promise<void> {
  if (!Number.isFinite(chatId) || chatId === 0) {
    throw new Error('Некорректный chat_id');
  }

  await withTransaction(async (client: PoolClient) => {
    const p = [chatId];

    await client.query('DELETE FROM receipts WHERE chat_id = $1', p);
    await client.query('DELETE FROM payouts WHERE chat_id = $1', p);
    await client.query('DELETE FROM exchange_rates WHERE chat_id = $1', p);
    await client.query('DELETE FROM retention_rates WHERE chat_id = $1', p);
    await client.query(
      'DELETE FROM linked_groups WHERE chat_id = $1 OR linked_group_id = $1',
      p
    );
    await client.query('DELETE FROM group_settings WHERE chat_id = $1', p);
    await client.query('DELETE FROM broadcast_chats WHERE chat_id = $1', p);
    await client.query('DELETE FROM broadcast_inaccessible WHERE chat_id = $1', p);
    await client.query('DELETE FROM broadcast_always_exclude WHERE chat_id = $1', p);
    await client.query('DELETE FROM admin_chat_invite_links WHERE chat_id = $1', p);
    await client.query('DELETE FROM processed_transactions WHERE chat_id = $1', p);
    await client.query(
      `UPDATE connections SET is_active = FALSE
       WHERE client_group_id = $1 OR verifier_group_id = $1`,
      p
    );
    await client.query(
      'UPDATE anonymous_chats SET verifier_group_id = NULL WHERE verifier_group_id = $1',
      p
    );
  });
}
