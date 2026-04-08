import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { assertAdmin } from '@/lib/api-guard';

export interface AdminChatRow {
  chat_id: number;
  name: string | null;
  in_group_settings: boolean;
  as_client_in_connection: boolean;
  as_verifier_in_connection: boolean;
  invite_link: string | null;
}

/** Все чаты, с которых бот ведёт учёт / рассылку (как в list_all_broadcast_chat_ids). Только admin. */
export async function GET(request: NextRequest) {
  const denied = await assertAdmin(request);
  if (denied) return denied;

  try {
    await query(`
      CREATE TABLE IF NOT EXISTS admin_chat_invite_links (
        chat_id BIGINT PRIMARY KEY,
        invite_link TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    const { rows } = await query<{
      cid: string;
      name: string | null;
      in_group_settings: boolean;
      as_client: boolean;
      as_verifier: boolean;
      invite_link: string | null;
    }>(
      `
      WITH ids AS (
        SELECT DISTINCT cid FROM (
          SELECT chat_id AS cid FROM group_settings
          UNION
          SELECT chat_id AS cid FROM broadcast_chats
          UNION
          SELECT client_group_id AS cid FROM connections WHERE is_active = TRUE
          UNION
          SELECT verifier_group_id AS cid FROM connections WHERE is_active = TRUE
        ) s
      )
      SELECT
        i.cid::text,
        NULLIF(TRIM(b.name), '') AS name,
        EXISTS (SELECT 1 FROM group_settings g WHERE g.chat_id = i.cid) AS in_group_settings,
        EXISTS (
          SELECT 1 FROM connections c WHERE c.is_active = TRUE AND c.client_group_id = i.cid
        ) AS as_client,
        EXISTS (
          SELECT 1 FROM connections c WHERE c.is_active = TRUE AND c.verifier_group_id = i.cid
        ) AS as_verifier,
        NULLIF(TRIM(l.invite_link), '') AS invite_link
      FROM ids i
      LEFT JOIN broadcast_chats b ON b.chat_id = i.cid
      LEFT JOIN admin_chat_invite_links l ON l.chat_id = i.cid
      ORDER BY i.cid
      `
    );

    const chats: AdminChatRow[] = rows.map((r) => ({
      chat_id: Number(r.cid),
      name: r.name,
      in_group_settings: r.in_group_settings,
      as_client_in_connection: r.as_client,
      as_verifier_in_connection: r.as_verifier,
      invite_link: r.invite_link,
    }));

    return NextResponse.json({ chats });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Ошибка';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
