import { NextRequest, NextResponse } from 'next/server';
import { getSessionFromRequest, appendAudit } from '@/lib/auth';
import { query } from '@/lib/db';
import { verifySync } from 'otplib';

export async function POST(request: NextRequest) {
  const session = await getSessionFromRequest(request);
  if (!session || session.role !== 'admin') {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const body = await request.json();
  const code = typeof body.code === 'string' ? body.code.trim() : '';
  if (!code) {
    return NextResponse.json({ error: 'Нужен code из приложения-аутентификатора' }, { status: 400 });
  }

  const uid = parseInt(session.sub, 10);
  const { rows } = await query<{ totp_secret: string | null }>(
    'SELECT totp_secret FROM crm_users WHERE id = $1',
    [uid]
  );
  const row = rows[0];
  if (!row?.totp_secret) {
    return NextResponse.json({ error: 'Сначала POST /api/auth/2fa/setup' }, { status: 400 });
  }
  const vr = verifySync({ token: code, secret: row.totp_secret });
  if (!vr.valid) {
    return NextResponse.json({ error: 'Неверный код' }, { status: 400 });
  }
  await query('UPDATE crm_users SET totp_enabled = 1 WHERE id = $1', [uid]);

  await appendAudit(uid, '2fa_enabled', session.email);
  return NextResponse.json({ success: true });
}
