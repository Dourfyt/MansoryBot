import { NextRequest, NextResponse } from 'next/server';
import { countUsers, hashPassword, insertUser, appendAudit } from '@/lib/auth';
import { query } from '@/lib/db';

/** Первичное создание admin (только если crm_users пуста и секрет совпал). */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const secret = typeof body.secret === 'string' ? body.secret : '';
    const email = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
    const password = typeof body.password === 'string' ? body.password : '';

    const expected = process.env.CRM_BOOTSTRAP_SECRET?.trim();
    if (!expected || secret !== expected) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    if (!email || !password || password.length < 8) {
      return NextResponse.json({ error: 'Нужны email и пароль (мин. 8 символов)' }, { status: 400 });
    }

    const n = await countUsers();
    if (n > 0) {
      return NextResponse.json({ error: 'Пользователи уже созданы' }, { status: 400 });
    }

    const hash = await hashPassword(password);
    const id = await insertUser(email, hash, 'admin');

    const tok = (process.env.BOT_TOKEN || process.env.GROUP_CONNECTOR_BOT_TOKEN || '').trim();
    if (tok) {
      await query(
        `INSERT INTO bot_instances (id, label, telegram_bot_token, is_active)
         VALUES (1, 'primary', $1, 1)
         ON CONFLICT (id) DO NOTHING`,
        [tok]
      );
    }

    await appendAudit(id, 'bootstrap_admin', email);
    return NextResponse.json({ success: true, message: 'Администратор создан. Войдите через /login.' });
  } catch (error) {
    console.error('Bootstrap error:', error);
    return NextResponse.json({ error: 'Ошибка сервера' }, { status: 500 });
  }
}
