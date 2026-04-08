import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { assertAdmin } from '@/lib/api-guard';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';

/** Список логических ботов и смена токена (только admin). */
export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdmin(request);
    if (denied) return denied;

    const { rows } = await query<{
      id: number;
      label: string;
      is_active: number;
      created_at: string;
      has_token: boolean;
    }>(
      `SELECT id, label, is_active, created_at,
        (telegram_bot_token IS NOT NULL AND length(trim(telegram_bot_token)) > 0) AS has_token
       FROM bot_instances ORDER BY id`
    );
    return NextResponse.json({ instances: rows });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : 'Ошибка' }, { status: 500 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const denied = await assertAdmin(request);
    if (denied) return denied;

    const body = await request.json();
    const id = typeof body.id === 'number' ? body.id : parseInt(String(body.id), 10);
    const token = typeof body.telegram_bot_token === 'string' ? body.telegram_bot_token.trim() : '';
    if (!id || !token) {
      return NextResponse.json({ error: 'Нужны id и telegram_bot_token' }, { status: 400 });
    }

    await query('UPDATE bot_instances SET telegram_bot_token = $1 WHERE id = $2', [token, id]);

    const sess = await getSessionFromRequest(request);
    await appendAudit(sess ? parseInt(sess.sub, 10) : null, 'bot_token_rotated', `instance_id=${id}`);
    return NextResponse.json({
      success: true,
      message:
        'Токен сохранён в базе. Процесс бота подхватит его автоматически в течение ~15 секунд (polling).',
    });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : 'Ошибка' }, { status: 500 });
  }
}
