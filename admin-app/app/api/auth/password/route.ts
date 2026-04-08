import { NextRequest, NextResponse } from 'next/server';
import {
  findUserByEmail,
  verifyPassword,
  signSessionJwt,
  rateLimitLogin,
  appendAudit,
  countUsers,
} from '@/lib/auth';
import { verifySync } from 'otplib';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const email = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
    const password = typeof body.password === 'string' ? body.password : '';
    const totp = typeof body.totp === 'string' ? body.totp.trim() : '';

    if (!email || !password) {
      return NextResponse.json({ error: 'Укажите email и пароль' }, { status: 400 });
    }

    const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || request.ip || 'unknown';
    const rl = rateLimitLogin(`${ip}:${email}`);
    if (!rl.ok) {
      return NextResponse.json({ error: 'Слишком много попыток. Подождите 15 минут.' }, { status: 429 });
    }

    const userCount = await countUsers();
    if (userCount === 0) {
      return NextResponse.json(
        {
          error:
            'Пользователи не созданы. Сначала выполните POST /api/auth/bootstrap с CRM_BOOTSTRAP_SECRET.',
        },
        { status: 401 }
      );
    }

    const user = await findUserByEmail(email);
    if (!user || !(await verifyPassword(user.password_hash, password))) {
      return NextResponse.json({ error: 'Неверный email или пароль' }, { status: 401 });
    }

    if (user.totp_enabled && user.totp_secret) {
      if (!totp) {
        return NextResponse.json({ error: 'Требуется код 2FA', requiresTotp: true }, { status: 401 });
      }
      const vr = verifySync({ token: totp, secret: user.totp_secret });
      if (!vr.valid) {
        return NextResponse.json({ error: 'Неверный код 2FA' }, { status: 401 });
      }
    }

    const jwt = await signSessionJwt(user.id, user.email, user.role);
    const response = NextResponse.json({ success: true, message: 'Авторизация успешна', role: user.role });

    response.cookies.set('sessionToken', jwt, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 24 * 60 * 60,
      path: '/',
    });

    await appendAudit(user.id, 'login', email);
    return response;
  } catch (error) {
    console.error('Auth error:', error);
    return NextResponse.json({ error: 'Ошибка сервера' }, { status: 500 });
  }
}
