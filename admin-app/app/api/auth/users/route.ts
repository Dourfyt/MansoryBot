import { NextRequest, NextResponse } from 'next/server';
import { assertAdmin } from '@/lib/api-guard';
import { hashPassword, insertUser, appendAudit, getSessionFromRequest } from '@/lib/auth';
import { query } from '@/lib/db';
import { normalizePermissionsInput } from '@/lib/support-permissions';

/** Список пользователей CRM (только admin). */
export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdmin(request);
    if (denied) return denied;

    const { rows } = await query<{
      id: number;
      email: string;
      role: string;
      created_at: string | null;
      telegram_user_id: string | null;
      support_permissions: unknown;
    }>(
      'SELECT id, email, role, created_at, telegram_user_id::text AS telegram_user_id, support_permissions FROM crm_users ORDER BY id'
    );
    return NextResponse.json({
      users: rows.map((r) => ({
        ...r,
        telegram_user_id:
          r.telegram_user_id != null && r.telegram_user_id !== ''
            ? Number(r.telegram_user_id)
            : null,
        support_permissions:
          r.role === 'support' ? r.support_permissions ?? null : null,
      })),
    });
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'message' in e ? String((e as Error).message) : 'Ошибка';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

/** Создать пользователя support (только admin). */
export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdmin(request);
    if (denied) return denied;

    const body = await request.json();
    const email = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
    const password = typeof body.password === 'string' ? body.password : '';
    const tgRaw = body.telegram_user_id;
    const tgParsed =
      typeof tgRaw === 'number'
        ? tgRaw
        : typeof tgRaw === 'string'
          ? parseInt(tgRaw.trim(), 10)
          : NaN;

    if (!email || !password || password.length < 8) {
      return NextResponse.json({ error: 'Нужны email и пароль (не короче 8 символов)' }, { status: 400 });
    }
    if (!Number.isFinite(tgParsed) || tgParsed < 1) {
      return NextResponse.json(
        { error: 'Укажите числовой Telegram ID сотрудника (например из @userinfobot)' },
        { status: 400 }
      );
    }

    const perms = normalizePermissionsInput(body.support_permissions);
    const hash = await hashPassword(password);
    const id = await insertUser(email, hash, 'support', tgParsed, JSON.stringify(perms));
    const sess = await getSessionFromRequest(request);
    await appendAudit(sess ? parseInt(sess.sub, 10) : null, 'crm_user_created', `${email} support`);
    return NextResponse.json({ success: true, id });
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'message' in e ? String((e as Error).message) : 'Ошибка';
    if (msg.includes('UNIQUE')) {
      return NextResponse.json({ error: 'Email уже занят' }, { status: 400 });
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
