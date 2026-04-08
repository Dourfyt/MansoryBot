import { NextRequest, NextResponse } from 'next/server';
import { assertAdmin } from '@/lib/api-guard';
import { appendAudit, getSessionFromRequest, hashPassword } from '@/lib/auth';
import { query } from '@/lib/db';
import { normalizePermissionsInput } from '@/lib/support-permissions';

export async function PATCH(
  request: NextRequest,
  context: { params: { id: string } }
) {
  try {
    const denied = await assertAdmin(request);
    if (denied) return denied;

    const id = parseInt(context.params.id, 10);
    if (!Number.isFinite(id) || id < 1) {
      return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
    }

    const { rows: urows } = await query<{ role: string }>(
      'SELECT role FROM crm_users WHERE id = $1',
      [id]
    );
    const u = urows[0];
    if (!u) {
      return NextResponse.json({ error: 'Пользователь не найден' }, { status: 404 });
    }
    if (u.role !== 'support') {
      return NextResponse.json(
        { error: 'Редактировать можно только учётные записи с ролью support' },
        { status: 400 }
      );
    }

    const body = await request.json();
    const emailRaw = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
    const password = typeof body.password === 'string' ? body.password : '';
    const hasTg = Object.prototype.hasOwnProperty.call(body, 'telegram_user_id');

    let changed = false;

    if (emailRaw) {
      await query('UPDATE crm_users SET email = $1 WHERE id = $2 AND role = $3', [
        emailRaw,
        id,
        'support',
      ]);
      changed = true;
    }
    if (password) {
      if (password.length < 8) {
        return NextResponse.json({ error: 'Пароль не короче 8 символов' }, { status: 400 });
      }
      const hash = await hashPassword(password);
      await query('UPDATE crm_users SET password_hash = $1 WHERE id = $2 AND role = $3', [
        hash,
        id,
        'support',
      ]);
      changed = true;
    }

    if (hasTg) {
      const v = body.telegram_user_id;
      if (v === null || v === '') {
        await query('UPDATE crm_users SET telegram_user_id = NULL WHERE id = $1 AND role = $2', [
          id,
          'support',
        ]);
        changed = true;
      } else {
        const n = typeof v === 'number' ? v : parseInt(String(v).trim(), 10);
        if (!Number.isFinite(n) || n < 1) {
          return NextResponse.json({ error: 'Некорректный Telegram ID' }, { status: 400 });
        }
        await query('UPDATE crm_users SET telegram_user_id = $1 WHERE id = $2 AND role = $3', [
          n,
          id,
          'support',
        ]);
        changed = true;
      }
    }

    if (Object.prototype.hasOwnProperty.call(body, 'support_permissions')) {
      const perms = normalizePermissionsInput(body.support_permissions);
      await query(
        'UPDATE crm_users SET support_permissions = $1::jsonb WHERE id = $2 AND role = $3',
        [JSON.stringify(perms), id, 'support']
      );
      changed = true;
    }

    if (!changed) {
      return NextResponse.json(
        { error: 'Укажите email, пароль, telegram_user_id и/или support_permissions' },
        { status: 400 }
      );
    }

    const sess = await getSessionFromRequest(request);
    await appendAudit(sess ? parseInt(sess.sub, 10) : null, 'crm_user_updated', `id=${id}`);
    return NextResponse.json({ success: true });
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'message' in e ? String((e as Error).message) : 'Ошибка';
    if (msg.includes('UNIQUE')) {
      return NextResponse.json({ error: 'Email уже занят' }, { status: 400 });
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

export async function DELETE(
  request: NextRequest,
  context: { params: { id: string } }
) {
  try {
    const denied = await assertAdmin(request);
    if (denied) return denied;

    const id = parseInt(context.params.id, 10);
    if (!Number.isFinite(id) || id < 1) {
      return NextResponse.json({ error: 'Некорректный id' }, { status: 400 });
    }

    const sess = await getSessionFromRequest(request);
    if (sess && parseInt(sess.sub, 10) === id) {
      return NextResponse.json({ error: 'Нельзя удалить свою учётную запись' }, { status: 400 });
    }

    const { rows: urows } = await query<{ role: string }>(
      'SELECT role FROM crm_users WHERE id = $1',
      [id]
    );
    const u = urows[0];
    if (!u) {
      return NextResponse.json({ error: 'Пользователь не найден' }, { status: 404 });
    }
    if (u.role !== 'support') {
      return NextResponse.json(
        { error: 'Удалять можно только учётные записи support' },
        { status: 400 }
      );
    }

    const { rowCount } = await query('DELETE FROM crm_users WHERE id = $1 AND role = $2', [
      id,
      'support',
    ]);
    if (!rowCount) {
      return NextResponse.json({ error: 'Не удалось удалить' }, { status: 400 });
    }

    await appendAudit(sess ? parseInt(sess.sub, 10) : null, 'crm_user_deleted', `id=${id}`);
    return NextResponse.json({ success: true });
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'message' in e ? String((e as Error).message) : 'Ошибка';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
