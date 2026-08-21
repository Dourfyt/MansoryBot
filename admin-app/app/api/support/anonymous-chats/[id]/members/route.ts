import { NextRequest, NextResponse } from 'next/server';
import { query, withTransaction } from '@/lib/db';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';
import { assertAnonymousChatsApi } from '@/lib/api-guard';
import { anonymousChatsEmptyGetResponse } from '@/lib/anonymous-chats-feature';

export async function GET(
  request: NextRequest,
  context: { params: { id: string } }
) {
  const empty = anonymousChatsEmptyGetResponse({ members: [] });
  if (empty) return empty;
  const denied = await assertAnonymousChatsApi(request);
  if (denied) return denied;

  const chatId = parseInt(context.params.id, 10);
  if (!Number.isFinite(chatId)) {
    return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
  }

  const { rows: exists } = await query<{ id: number }>(
    'SELECT id FROM anonymous_chats WHERE id = $1',
    [chatId]
  );
  if (!exists.length) {
    return NextResponse.json({ error: 'Чат не найден' }, { status: 404 });
  }

  const { rows } = await query<{
    telegram_user_id: string;
    nickname: string;
    joined_at: string;
  }>(
    `
    SELECT
      m.telegram_user_id::text AS telegram_user_id,
      m.nickname,
      m.joined_at::text AS joined_at
    FROM anonymous_chat_members m
    WHERE m.anonymous_chat_id = $1
    ORDER BY m.joined_at DESC NULLS LAST, m.telegram_user_id DESC
    `,
    [chatId]
  );

  return NextResponse.json({
    members: rows.map((r) => ({
      telegram_user_id: Number(r.telegram_user_id),
      nickname: r.nickname,
      joined_at: r.joined_at,
    })),
  });
}

export async function DELETE(
  request: NextRequest,
  context: { params: { id: string } }
) {
  const denied = await assertAnonymousChatsApi(request);
  if (denied) return denied;

  const session = await getSessionFromRequest(request);
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const crmUserId = parseInt(session.sub, 10);
  if (!Number.isFinite(crmUserId)) {
    return NextResponse.json({ error: 'Invalid session' }, { status: 400 });
  }

  const chatId = parseInt(context.params.id, 10);
  if (!Number.isFinite(chatId)) {
    return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
  }

  const url = new URL(request.url);
  const rawTgId = url.searchParams.get('telegram_user_id');
  const telegramUserId = parseInt(rawTgId || '', 10);
  if (!Number.isFinite(telegramUserId)) {
    return NextResponse.json(
      { error: 'Укажите telegram_user_id (query)' },
      { status: 400 }
    );
  }

  try {
    await withTransaction(async (client) => {
      const { rowCount } = await client.query(
        `
        DELETE FROM anonymous_chat_members
        WHERE anonymous_chat_id = $1 AND telegram_user_id = $2
        `,
        [chatId, telegramUserId]
      );

      if (!rowCount) {
        const err: Error & { statusCode?: number } = new Error('not_found');
        err.statusCode = 404;
        throw err;
      }

      // Как leave_room(): если это активная комната в ЛС — переключить или очистить.
      const activeRes = await client.query(
        `
        SELECT anonymous_chat_id
        FROM anonymous_dm_active_room
        WHERE telegram_user_id = $1
        `,
        [telegramUserId]
      );
      const activeRow = activeRes.rows?.[0] as { anonymous_chat_id: number } | undefined;
      if (activeRow && Number(activeRow.anonymous_chat_id) === chatId) {
        const nextRes = await client.query(
          `
          SELECT anonymous_chat_id
          FROM anonymous_chat_members
          WHERE telegram_user_id = $1
          ORDER BY joined_at DESC NULLS LAST, anonymous_chat_id DESC
          LIMIT 1
          `,
          [telegramUserId]
        );
        const nextRow = nextRes.rows?.[0] as { anonymous_chat_id: number } | undefined;
        if (nextRow) {
          await client.query(
            `
            UPDATE anonymous_dm_active_room
            SET anonymous_chat_id = $1, updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = $2
            `,
            [nextRow.anonymous_chat_id, telegramUserId]
          );
        } else {
          await client.query(
            'DELETE FROM anonymous_dm_active_room WHERE telegram_user_id = $1',
            [telegramUserId]
          );
        }
      }
    });
  } catch (e) {
    if (e instanceof Error && (e as Error & { statusCode?: number }).statusCode === 404) {
      return NextResponse.json({ error: 'Участник не найден' }, { status: 404 });
    }
    throw e;
  }

  const { rows: countRows } = await query<{ c: string }>(
    'SELECT COUNT(*)::text AS c FROM anonymous_chat_members WHERE anonymous_chat_id = $1',
    [chatId]
  );
  const memberCount = parseInt(countRows[0]?.c || '0', 10) || 0;

  await appendAudit(crmUserId, 'anonymous_chat_kick_member', `${chatId}:${telegramUserId}`);

  return NextResponse.json({ ok: true, member_count: memberCount });
}
