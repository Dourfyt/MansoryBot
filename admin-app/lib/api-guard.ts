import { NextRequest, NextResponse } from 'next/server';
import { getSessionFromRequest, requireAdmin } from './auth';
import { getSupportPermissionsByUserId, type SupportPermissions } from './support-permissions';
import {
  anonymousChatsDisabledResponse,
  isAnonymousChatsEnabled,
} from './anonymous-chats-feature';

/** Только admin: CRM-пользователи, токен бота и т.п. */
export async function assertAdmin(request: NextRequest): Promise<NextResponse | null> {
  const s = await requireAdmin(request);
  if (!s) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  return null;
}

/** Admin или support с указанным правом. */
export async function assertAdminOrSupportPermission(
  request: NextRequest,
  perm: keyof SupportPermissions
): Promise<NextResponse | null> {
  const s = await getSessionFromRequest(request);
  if (!s) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  if (s.role === 'admin') {
    return null;
  }
  if (s.role !== 'support') {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  const userId = parseInt(s.sub, 10);
  if (!Number.isFinite(userId)) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  const permissions = await getSupportPermissionsByUserId(userId);
  if (!permissions[perm]) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  return null;
}

/** Фича выключена — 404 без тела (не сообщаем, что фича отключена). */
export function assertAnonymousChatsEnabled(): NextResponse | null {
  if (!isAnonymousChatsEnabled()) {
    return anonymousChatsDisabledResponse();
  }
  return null;
}

/** Права support/admin + фича анонимных чатов включена. */
export async function assertAnonymousChatsApi(
  request: NextRequest,
): Promise<NextResponse | null> {
  const featureOff = assertAnonymousChatsEnabled();
  if (featureOff) return featureOff;
  return assertAdminOrSupportPermission(request, 'anonymous');
}
