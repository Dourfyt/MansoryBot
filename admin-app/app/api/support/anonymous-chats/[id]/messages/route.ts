import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { assertAnonymousChatsApi } from '@/lib/api-guard';
import { anonymousChatsEmptyGetResponse } from '@/lib/anonymous-chats-feature';

export async function GET(
  request: NextRequest,
  context: { params: { id: string } }
) {
  const empty = anonymousChatsEmptyGetResponse({ messages: [] });
  if (empty) return empty;
  const denied = await assertAnonymousChatsApi(request);
  if (denied) return denied;

  const chatId = parseInt(context.params.id, 10);
  if (!Number.isFinite(chatId)) {
    return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
  }

  const { rows: exists } = await query<{ id: number }>('SELECT id FROM anonymous_chats WHERE id = $1', [chatId]);
  if (!exists.length) {
    return NextResponse.json({ error: 'Чат не найден' }, { status: 404 });
  }

  const mq = (request.nextUrl.searchParams.get('q') ?? '').trim();

  const { rows } = await query<{
    id: number;
    nickname: string;
    body: string;
    from_telegram_user_id: string;
    created_at: string;
  }>(
    `
    SELECT m.id, m.nickname, m.body, m.from_telegram_user_id::text, m.created_at
    FROM anonymous_chat_messages m
    WHERE m.anonymous_chat_id = $1
      AND (
        $2::text = ''
        OR m.body ILIKE '%' || $2 || '%'
        OR m.nickname ILIKE '%' || $2 || '%'
        OR m.from_telegram_user_id::text LIKE '%' || $2 || '%'
      )
    ORDER BY m.created_at ASC
    LIMIT 500
    `,
    [chatId, mq]
  );

  return NextResponse.json({
    messages: rows.map((r) => ({
      id: r.id,
      nickname: r.nickname,
      body: r.body,
      from_telegram_user_id: Number(r.from_telegram_user_id),
      created_at: r.created_at,
    })),
  });
}
