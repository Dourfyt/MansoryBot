import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { assertAdmin } from '@/lib/api-guard';

export interface InaccessibleChatRow {
  chat_id: number;
  name: string | null;
}

/** Чаты, помеченные как недоступные для бота (после проверки). */
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

    const { rows } = await query<{ chat_id: string; name: string | null }>(
      `
      SELECT bi.chat_id::text, NULLIF(TRIM(b.name), '') AS name
      FROM broadcast_inaccessible bi
      LEFT JOIN broadcast_chats b ON b.chat_id = bi.chat_id
      ORDER BY bi.chat_id
      `
    );

    const chats: InaccessibleChatRow[] = rows.map((r) => ({
      chat_id: Number(r.chat_id),
      name: r.name,
    }));

    return NextResponse.json({ chats });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Ошибка';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
