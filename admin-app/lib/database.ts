import { query } from './db';
import { resolveBotId, resolveBotToken } from './resolve-bot-token';

export interface Connection {
  id: number;
  client_group_id: number;
  verifier_group_id: number;
  client_group_name: string | null;
  verifier_group_name: string | null;
  created_at: string;
  is_active: boolean;
}

export interface ConnectionStats {
  total: number;
  active: number;
  inactive: number;
  unique_verifiers: number;
  unique_clients: number;
}

export async function getAllConnections(inactive: boolean = false): Promise<Connection[]> {
  const sql = inactive
    ? `SELECT id, client_group_id, verifier_group_id, client_group_name, verifier_group_name,
              created_at, is_active
       FROM connections
       WHERE is_active = FALSE
       ORDER BY created_at DESC`
    : `SELECT id, client_group_id, verifier_group_id, client_group_name, verifier_group_name,
              created_at, is_active
       FROM connections
       WHERE is_active = TRUE
       ORDER BY created_at DESC`;

  const { rows } = await query<Connection>(sql);
  return rows;
}

export async function addConnection(
  client_group_id: number,
  verifier_group_id: number
): Promise<boolean> {
  try {
    await query(
      `INSERT INTO connections (client_group_id, verifier_group_id, is_active)
       VALUES ($1, $2, TRUE)
       ON CONFLICT (client_group_id, verifier_group_id)
       DO UPDATE SET is_active = TRUE`,
      [client_group_id, verifier_group_id]
    );

    try {
      const botToken = await resolveBotToken();

      const clientGroupResponse = await fetch(
        `https://api.telegram.org/bot${botToken}/getChat?chat_id=${client_group_id}`
      );
      const clientGroupData = await clientGroupResponse.json();

      let clientGroupName: string | null = null;
      if (clientGroupData.ok) {
        clientGroupName =
          clientGroupData.result.title ||
          clientGroupData.result.first_name ||
          clientGroupData.result.username;
      }

      const verifierGroupResponse = await fetch(
        `https://api.telegram.org/bot${botToken}/getChat?chat_id=${verifier_group_id}`
      );
      const verifierGroupData = await verifierGroupResponse.json();

      let verifierGroupName: string | null = null;
      if (verifierGroupData.ok) {
        verifierGroupName =
          verifierGroupData.result.title ||
          verifierGroupData.result.first_name ||
          verifierGroupData.result.username;
      }

      if (clientGroupName || verifierGroupName) {
        await query(
          `UPDATE connections
           SET client_group_name = COALESCE($1, client_group_name),
               verifier_group_name = COALESCE($2, verifier_group_name)
           WHERE client_group_id = $3 AND verifier_group_id = $4`,
          [clientGroupName, verifierGroupName, client_group_id, verifier_group_id]
        );
      }
    } catch (apiError) {
      console.error('Ошибка при получении названий групп:', apiError);
    }

    return true;
  } catch (error) {
    console.error('Ошибка при добавлении связи:', error);
    return false;
  }
}

export async function deleteConnectionPermanently(
  client_group_id: number,
  verifier_group_id: number
): Promise<boolean> {
  try {
    const { rows } = await query<{ id: number }>(
      `SELECT id FROM connections WHERE client_group_id = $1 AND verifier_group_id = $2`,
      [client_group_id, verifier_group_id]
    );
    if (!rows.length) {
      return false;
    }
    const { rowCount } = await query(
      `DELETE FROM connections WHERE client_group_id = $1 AND verifier_group_id = $2`,
      [client_group_id, verifier_group_id]
    );
    return rowCount > 0;
  } catch (error) {
    console.error('Ошибка при полном удалении связи:', error);
    return false;
  }
}

export async function removeConnection(
  client_group_id: number,
  verifier_group_id: number
): Promise<boolean> {
  try {
    const { rows } = await query(
      `SELECT 1 FROM connections WHERE client_group_id = $1 AND verifier_group_id = $2`,
      [client_group_id, verifier_group_id]
    );
    if (!rows.length) {
      return false;
    }
    const { rowCount } = await query(
      `UPDATE connections SET is_active = FALSE WHERE client_group_id = $1 AND verifier_group_id = $2`,
      [client_group_id, verifier_group_id]
    );
    return rowCount > 0;
  } catch (error) {
    console.error('Ошибка при удалении связи:', error);
    return false;
  }
}

export async function updateGroupId(old_group_id: number, new_group_id: number): Promise<boolean> {
  try {
    const { rowCount } = await query(
      `UPDATE connections
       SET client_group_id = CASE WHEN client_group_id = $1 THEN $2 ELSE client_group_id END,
           verifier_group_id = CASE WHEN verifier_group_id = $1 THEN $2 ELSE verifier_group_id END
       WHERE client_group_id = $3 OR verifier_group_id = $3`,
      [old_group_id, new_group_id, old_group_id]
    );
    return rowCount > 0;
  } catch (error) {
    console.error('Ошибка при обновлении ID группы:', error);
    return false;
  }
}

export async function restoreConnection(
  client_group_id: number,
  verifier_group_id: number
): Promise<boolean> {
  try {
    const { rowCount } = await query(
      `UPDATE connections SET is_active = TRUE WHERE client_group_id = $1 AND verifier_group_id = $2`,
      [client_group_id, verifier_group_id]
    );
    return rowCount > 0;
  } catch (error) {
    console.error('Ошибка при восстановлении связи:', error);
    return false;
  }
}

export async function bulkRestoreConnections(
  items: { client_group_id: number; verifier_group_id: number }[]
): Promise<{ restored: number }> {
  let restored = 0;
  for (const { client_group_id, verifier_group_id } of items) {
    const ok = await restoreConnection(client_group_id, verifier_group_id);
    if (ok) restored++;
  }
  return { restored };
}

export async function bulkDeactivateConnections(
  items: { client_group_id: number; verifier_group_id: number }[]
): Promise<{ deactivated: number }> {
  let deactivated = 0;
  for (const { client_group_id, verifier_group_id } of items) {
    const ok = await removeConnection(client_group_id, verifier_group_id);
    if (ok) deactivated++;
  }
  return { deactivated };
}

export async function bulkDeleteConnections(
  items: { client_group_id: number; verifier_group_id: number }[]
): Promise<{ deleted: number }> {
  let deleted = 0;
  for (const { client_group_id, verifier_group_id } of items) {
    const ok = await deleteConnectionPermanently(client_group_id, verifier_group_id);
    if (ok) deleted++;
  }
  return { deleted };
}

export async function updateGroupNames(): Promise<{ updated: number; errors: number }> {
  let updated = 0;
  let errors = 0;

  try {
    const { rows: connections } = await query<{ client_group_id: number; verifier_group_id: number }>(
      `SELECT client_group_id, verifier_group_id FROM connections WHERE is_active = TRUE`
    );

    const botToken = await resolveBotToken();

    for (const connection of connections) {
      try {
        const clientGroupResponse = await fetch(
          `https://api.telegram.org/bot${botToken}/getChat?chat_id=${connection.client_group_id}`
        );
        const clientGroupData = await clientGroupResponse.json();

        let clientGroupName: string | null = null;
        if (clientGroupData.ok) {
          clientGroupName =
            clientGroupData.result.title ||
            clientGroupData.result.first_name ||
            clientGroupData.result.username;
        }

        const verifierGroupResponse = await fetch(
          `https://api.telegram.org/bot${botToken}/getChat?chat_id=${connection.verifier_group_id}`
        );
        const verifierGroupData = await verifierGroupResponse.json();

        let verifierGroupName: string | null = null;
        if (verifierGroupData.ok) {
          verifierGroupName =
            verifierGroupData.result.title ||
            verifierGroupData.result.first_name ||
            verifierGroupData.result.username;
        }

        if (clientGroupName || verifierGroupName) {
          await query(
            `UPDATE connections
             SET client_group_name = COALESCE($1, client_group_name),
                 verifier_group_name = COALESCE($2, verifier_group_name)
             WHERE client_group_id = $3 AND verifier_group_id = $4`,
            [clientGroupName, verifierGroupName, connection.client_group_id, connection.verifier_group_id]
          );
          updated++;
        }
      } catch (error) {
        console.error(
          `Ошибка при обновлении названий для связи ${connection.client_group_id} ↔ ${connection.verifier_group_id}:`,
          error
        );
        errors++;
      }
    }
  } catch (error) {
    console.error('Ошибка при обновлении названий групп:', error);
    errors++;
  }

  return { updated, errors };
}

export async function getConnectionStats(): Promise<ConnectionStats> {
  const total = await query<{ count: string }>('SELECT COUNT(*)::int AS count FROM connections');
  const active = await query<{ count: string }>(
    'SELECT COUNT(*)::int AS count FROM connections WHERE is_active = TRUE'
  );
  const inactive = await query<{ count: string }>(
    'SELECT COUNT(*)::int AS count FROM connections WHERE is_active = FALSE'
  );
  const unique_verifiers = await query<{ count: string }>(
    'SELECT COUNT(DISTINCT verifier_group_id)::int AS count FROM connections WHERE is_active = TRUE'
  );
  const unique_clients = await query<{ count: string }>(
    'SELECT COUNT(DISTINCT client_group_id)::int AS count FROM connections WHERE is_active = TRUE'
  );

  return {
    total: Number(total.rows[0]?.count ?? 0),
    active: Number(active.rows[0]?.count ?? 0),
    inactive: Number(inactive.rows[0]?.count ?? 0),
    unique_verifiers: Number(unique_verifiers.rows[0]?.count ?? 0),
    unique_clients: Number(unique_clients.rows[0]?.count ?? 0),
  };
}

export interface WelcomeLink {
  label: string;
  url: string;
}

export async function getWelcome(): Promise<{ welcome_message: string; welcome_links: WelcomeLink[] }> {
  const { rows } = await query<{ welcome_message: string | null; welcome_links: string | null }>(
    'SELECT welcome_message, welcome_links FROM global_settings WHERE id = 1'
  );
  const row = rows[0];
  let welcome_message = '';
  let welcome_links: WelcomeLink[] = [];
  if (row) {
    welcome_message = row.welcome_message || '';
    if (row.welcome_links) {
      try {
        const parsed = JSON.parse(row.welcome_links);
        if (Array.isArray(parsed)) {
          welcome_links = parsed
            .filter((x: unknown) => x && typeof x === 'object' && typeof (x as WelcomeLink).url === 'string')
            .map((x: { label?: string; url?: string }) => ({
              label: typeof (x as WelcomeLink).label === 'string' ? (x as WelcomeLink).label : 'Ссылка',
              url: (x as WelcomeLink).url,
            }));
        }
      } catch (_) {}
    }
  }
  return { welcome_message, welcome_links };
}

export async function setWelcome(welcome_message: string, welcome_links: WelcomeLink[]): Promise<void> {
  const linksJson = JSON.stringify(welcome_links);
  await query(
    `INSERT INTO global_settings (id, welcome_message, welcome_links, updated_at)
     VALUES (1, $1, $2, CURRENT_TIMESTAMP)
     ON CONFLICT (id) DO UPDATE SET
       welcome_message = EXCLUDED.welcome_message,
       welcome_links = EXCLUDED.welcome_links,
       updated_at = CURRENT_TIMESTAMP`,
    [welcome_message, linksJson]
  );
}

export interface BroadcastGroup {
  chat_id: number;
  name: string | null;
  role: 'client' | 'verifier' | 'group';
}

export async function getBroadcastGroups(): Promise<BroadcastGroup[]> {
  const { rows } = await query<{ chat_id: string; name: string | null }>(`
    SELECT b.chat_id, b.name
    FROM broadcast_chats b
    LEFT JOIN broadcast_inaccessible i ON b.chat_id = i.chat_id
    WHERE i.chat_id IS NULL
    ORDER BY b.chat_id
  `);
  return rows.map((r) => ({
    chat_id: Number(r.chat_id),
    name: r.name?.trim() || null,
    role: 'group' as const,
  }));
}

async function ensureBroadcastAlwaysExcludeTable(): Promise<void> {
  await query(`
    CREATE TABLE IF NOT EXISTS broadcast_always_exclude (
      chat_id BIGINT PRIMARY KEY
    )
  `);
}

export async function getBroadcastAlwaysExcludeChatIds(): Promise<number[]> {
  await ensureBroadcastAlwaysExcludeTable();
  const { rows } = await query<{ chat_id: string }>(
    `SELECT chat_id FROM broadcast_always_exclude ORDER BY chat_id`
  );
  return rows.map((r) => Number(r.chat_id));
}

export async function setBroadcastAlwaysExcludeChatIds(ids: number[]): Promise<void> {
  await ensureBroadcastAlwaysExcludeTable();
  const unique = [...new Set(ids)].filter((id) => Number.isFinite(id) && Number.isInteger(id));
  await query(`DELETE FROM broadcast_always_exclude`);
  if (unique.length === 0) return;
  const placeholders = unique.map((_, i) => `($${i + 1})`).join(', ');
  await query(
    `INSERT INTO broadcast_always_exclude (chat_id) VALUES ${placeholders}`,
    unique
  );
}

export async function testConnection(
  client_group_id: number,
  verifier_group_id: number
): Promise<{ success: boolean; message: string }> {
  try {
    const { rows } = await query(
      `SELECT 1 FROM connections
       WHERE client_group_id = $1 AND verifier_group_id = $2 AND is_active = TRUE`,
      [client_group_id, verifier_group_id]
    );

    if (!rows.length) {
      return {
        success: false,
        message: 'Связь не найдена или неактивна в базе данных',
      };
    }

    const botToken = await resolveBotToken();
    const botId = await resolveBotId();

    try {
      const clientGroupResponse = await fetch(
        `https://api.telegram.org/bot${botToken}/getChat?chat_id=${client_group_id}`
      );
      const clientGroupData = await clientGroupResponse.json();

      if (!clientGroupData.ok) {
        return {
          success: false,
          message: `Бот не имеет доступа к группе клиентов (${client_group_id}): ${clientGroupData.description}`,
        };
      }

      const clientMemberResponse = await fetch(
        `https://api.telegram.org/bot${botToken}/getChatMember?chat_id=${client_group_id}&user_id=${botId}`
      );
      const clientMemberData = await clientMemberResponse.json();

      if (
        !clientMemberData.ok ||
        (clientMemberData.result.status !== 'administrator' && clientMemberData.result.status !== 'member')
      ) {
        return {
          success: false,
          message: `Бот не является участником группы клиентов (${client_group_id}). Статус: ${clientMemberData.result?.status || 'неизвестно'}`,
        };
      }

      const verifierGroupResponse = await fetch(
        `https://api.telegram.org/bot${botToken}/getChat?chat_id=${verifier_group_id}`
      );
      const verifierGroupData = await verifierGroupResponse.json();

      if (!verifierGroupData.ok) {
        return {
          success: false,
          message: `Бот не имеет доступа к группе проверяющих (${verifier_group_id}): ${verifierGroupData.description}`,
        };
      }

      const verifierMemberResponse = await fetch(
        `https://api.telegram.org/bot${botToken}/getChatMember?chat_id=${verifier_group_id}&user_id=${botId}`
      );
      const verifierMemberData = await verifierMemberResponse.json();

      if (
        !verifierMemberData.ok ||
        (verifierMemberData.result.status !== 'administrator' && verifierMemberData.result.status !== 'member')
      ) {
        return {
          success: false,
          message: `Бот не является участником группы проверяющих (${verifier_group_id}). Статус: ${verifierMemberData.result?.status || 'неизвестно'}`,
        };
      }

      const clientCanSendResponse = await fetch(
        `https://api.telegram.org/bot${botToken}/getChatMember?chat_id=${client_group_id}&user_id=${botId}`
      );
      const clientCanSendData = await clientCanSendResponse.json();

      const verifierCanSendResponse = await fetch(
        `https://api.telegram.org/bot${botToken}/getChatMember?chat_id=${verifier_group_id}&user_id=${botId}`
      );
      const verifierCanSendData = await verifierCanSendResponse.json();

      const clientCanSend = clientCanSendData.result?.can_send_messages !== false;
      const verifierCanSend = verifierCanSendData.result?.can_send_messages !== false;

      if (!clientCanSend || !verifierCanSend) {
        return {
          success: false,
          message: `Бот не может отправлять сообщения в ${!clientCanSend ? 'группу клиентов' : 'группу проверяющих'}`,
        };
      }

      return {
        success: true,
        message: `Связь активна и работает корректно. Бот имеет доступ к обеим группам и может отправлять сообщения.`,
      };
    } catch (apiError) {
      return {
        success: false,
        message: `Ошибка при проверке доступа через Telegram API: ${apiError}`,
      };
    }
  } catch (error) {
    return {
      success: false,
      message: `Ошибка при проверке связи: ${error}`,
    };
  }
}
