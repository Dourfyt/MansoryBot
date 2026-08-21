import { NextRequest, NextResponse } from 'next/server';
import { getSessionFromRequest } from '@/lib/auth';
import { query } from '@/lib/db';
import { generateSecret, generateURI } from 'otplib';

/** Генерация секрета 2FA (только admin). Клиент показывает otpauth URL в QR. */
export async function POST(request: NextRequest) {
  const session = await getSessionFromRequest(request);
  if (!session || session.role !== 'admin') {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const secret = generateSecret();
  const uid = parseInt(session.sub, 10);
  await query('UPDATE crm_users SET totp_secret = $1, totp_enabled = 0 WHERE id = $2', [secret, uid]);

  const otpauth = generateURI({
    issuer: 'MansoryCRM',
    label: session.email,
    secret,
  });
  return NextResponse.json({ otpauth, secret, message: 'Сохраните секрет, затем POST /api/auth/2fa/enable с кодом' });
}
