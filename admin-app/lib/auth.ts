import { NextRequest } from 'next/server';
import { SignJWT, jwtVerify } from 'jose';
import argon2 from 'argon2';
import crypto from 'crypto';
import { query } from './db';

export type CrmRole = 'admin' | 'support';

export interface SessionPayload {
  sub: string;
  email: string;
  role: CrmRole;
}

function getJwtSecretKey(): Uint8Array {
  const pepper = process.env.CRM_SESSION_PEPPER?.trim();
  if (!pepper || pepper.length < 16) {
    return new TextEncoder().encode('dev-only-unsafe-pepper-change-me');
  }
  return new TextEncoder().encode(pepper);
}

export async function signSessionJwt(userId: number, email: string, role: CrmRole): Promise<string> {
  return new SignJWT({ email, role })
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject(String(userId))
    .setIssuedAt()
    .setExpirationTime('24h')
    .sign(getJwtSecretKey());
}

export async function verifySessionJwt(token: string): Promise<SessionPayload | null> {
  try {
    const { payload } = await jwtVerify(token, getJwtSecretKey(), { algorithms: ['HS256'] });
    const sub = payload.sub;
    const email = typeof payload.email === 'string' ? payload.email : '';
    const role = payload.role === 'support' || payload.role === 'admin' ? payload.role : null;
    if (!sub || !email || !role) return null;
    return { sub, email, role };
  } catch {
    return null;
  }
}

/** Для API routes (Node): полная проверка JWT */
export async function getSessionFromRequest(request: NextRequest): Promise<SessionPayload | null> {
  const token = request.cookies.get('sessionToken')?.value;
  if (!token) return null;
  return verifySessionJwt(token);
}

export async function requireAdmin(request: NextRequest): Promise<SessionPayload | null> {
  const s = await getSessionFromRequest(request);
  if (!s || s.role !== 'admin') return null;
  return s;
}

export async function requireSupportOrAdmin(request: NextRequest): Promise<SessionPayload | null> {
  const s = await getSessionFromRequest(request);
  if (!s || (s.role !== 'admin' && s.role !== 'support')) return null;
  return s;
}

export async function hashPassword(plain: string): Promise<string> {
  return argon2.hash(plain, { type: argon2.argon2id });
}

export async function verifyPassword(hash: string, plain: string): Promise<boolean> {
  try {
    return await argon2.verify(hash, plain);
  } catch {
    return false;
  }
}

const loginAttempts = new Map<string, { n: number; reset: number }>();
const MAX_ATTEMPTS = 10;
const WINDOW_MS = 15 * 60 * 1000;

export function rateLimitLogin(key: string): { ok: boolean } {
  const now = Date.now();
  const cur = loginAttempts.get(key);
  if (!cur || now > cur.reset) {
    loginAttempts.set(key, { n: 1, reset: now + WINDOW_MS });
    return { ok: true };
  }
  if (cur.n >= MAX_ATTEMPTS) return { ok: false };
  cur.n += 1;
  return { ok: true };
}

export async function findUserByEmail(email: string): Promise<{
  id: number;
  email: string;
  password_hash: string;
  role: CrmRole;
  totp_enabled: number;
  totp_secret: string | null;
} | null> {
  const { rows } = await query<{
    id: number;
    email: string;
    password_hash: string;
    role: CrmRole;
    totp_enabled: number;
    totp_secret: string | null;
  }>('SELECT id, email, password_hash, role, totp_enabled, totp_secret FROM crm_users WHERE email = $1', [
    email.trim().toLowerCase(),
  ]);
  return rows[0] ?? null;
}

export async function countUsers(): Promise<number> {
  const { rows } = await query<{ c: string }>('SELECT COUNT(*)::int AS c FROM crm_users');
  return Number(rows[0]?.c ?? 0);
}

export async function insertUser(
  email: string,
  passwordHash: string,
  role: CrmRole,
  telegramUserId?: number | null,
  supportPermissionsJson?: string | null
): Promise<number> {
  const { rows } = await query<{ id: number }>(
    `INSERT INTO crm_users (email, password_hash, role, telegram_user_id, support_permissions)
     VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id`,
    [
      email.trim().toLowerCase(),
      passwordHash,
      role,
      telegramUserId ?? null,
      supportPermissionsJson ?? null,
    ]
  );
  return Number(rows[0]?.id);
}

export async function appendAudit(userId: number | null, action: string, detail?: string): Promise<void> {
  await query('INSERT INTO audit_log (user_id, action, detail) VALUES ($1, $2, $3)', [
    userId,
    action,
    detail ?? null,
  ]);
}

export function sha256hex(s: string): string {
  return crypto.createHash('sha256').update(s, 'utf8').digest('hex');
}
