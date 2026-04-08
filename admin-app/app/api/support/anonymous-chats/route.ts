import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function GET(request: NextRequest) {
  const denied = await assertAdminOrSupportPermission(request, 'anonymous');
  if (denied) return denied;

  const q = (request.nextUrl.searchParams.get('q') ?? '').trim();

  const { rows } = await query<{
    id: number;
    title: string;
    created_at: string;
    is_active: boolean;
    member_count: string;
    child_bot_username: string | null;
    verifier_group_id: string | null;
  }>(
    `
    SELECT c.id, c.title, c.created_at, c.is_active,
      NULLIF(TRIM(c.child_bot_username), '') AS child_bot_username,
      COALESCE(
        (SELECT COUNT(*)::text FROM anonymous_chat_members m WHERE m.anonymous_chat_id = c.id),
        '0'
      ) AS member_count,
      c.verifier_group_id::text AS verifier_group_id
    FROM anonymous_chats c
    WHERE (
      $1::text = ''
      OR c.title ILIKE '%' || $1 || '%'
      OR CAST(c.id AS TEXT) LIKE '%' || $1 || '%'
    )
    ORDER BY c.created_at DESC NULLS LAST
    LIMIT 200
    `,
    [q]
  );
  return NextResponse.json({
    chats: rows.map((r) => ({
      id: r.id,
      title: r.title,
      created_at: r.created_at,
      is_active: r.is_active,
      member_count: parseInt(r.member_count, 10) || 0,
      child_bot_username: r.child_bot_username,
      verifier_group_id:
        r.verifier_group_id != null && r.verifier_group_id !== ''
          ? Number(r.verifier_group_id)
          : null,
    })),
  });
}

export async function POST(request: NextRequest) {
  const denied = await assertAdminOrSupportPermission(request, 'anonymous');
  if (denied) return denied;
  const session = await getSessionFromRequest(request);
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const crmUserId = parseInt(session.sub, 10);
  if (!Number.isFinite(crmUserId)) {
    return NextResponse.json({ error: 'Invalid session' }, { status: 400 });
  }

  let body: { title?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Некорректный JSON' }, { status: 400 });
  }
  const title = typeof body.title === 'string' ? body.title.trim() : '';

  const { rows } = await query<{ id: number }>(
    `INSERT INTO anonymous_chats (title, created_by_crm_user_id)
     VALUES ($1, $2)
     RETURNING id`,
    [title || 'Без названия', crmUserId]
  );
  const id = rows[0]?.id;
  if (!id) {
    return NextResponse.json({ error: 'Не удалось создать чат' }, { status: 500 });
  }
  await appendAudit(crmUserId, 'anonymous_chat_create', String(id));
  return NextResponse.json({ id, title: title || 'Без названия' });
}
