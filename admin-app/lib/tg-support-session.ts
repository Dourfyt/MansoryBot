import { SignJWT, jwtVerify } from 'jose';

function getSecret(): Uint8Array {
  const p = process.env.CRM_SESSION_PEPPER?.trim();
  if (!p || p.length < 16) {
    return new TextEncoder().encode('dev-only-unsafe-pepper-change-me');
  }
  return new TextEncoder().encode(p);
}

export interface TgSupportPayload {
  sub: string;
  tid: number;
}

export async function signTgSupportToken(telegramUserId: number, ticketId: number): Promise<string> {
  return new SignJWT({ tid: ticketId })
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject(String(telegramUserId))
    .setIssuedAt()
    .setExpirationTime('30d')
    .setAudience('tg_support')
    .sign(getSecret());
}

export async function verifyTgSupportToken(token: string): Promise<TgSupportPayload | null> {
  try {
    const { payload } = await jwtVerify(token, getSecret(), {
      algorithms: ['HS256'],
      audience: 'tg_support',
    });
    const sub = payload.sub;
    const tid = payload.tid;
    if (!sub || typeof tid !== 'number' || !Number.isFinite(tid)) return null;
    return { sub, tid };
  } catch {
    return null;
  }
}
