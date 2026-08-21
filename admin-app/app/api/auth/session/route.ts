import { NextRequest, NextResponse } from 'next/server';
import { getSessionFromRequest } from '@/lib/auth';
import { isAnonymousChatsEnabled } from '@/lib/anonymous-chats-feature';
import { getSupportPermissionsByUserId } from '@/lib/support-permissions';

/** Текущая сессия: роль и права саппорта (у admin permissions = null, все разрешено на клиенте). */
export async function GET(request: NextRequest) {
  const session = await getSessionFromRequest(request);
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const uid = parseInt(session.sub, 10);
  const permissions =
    session.role === 'admin' ? null : await getSupportPermissionsByUserId(uid);
  return NextResponse.json({
    email: session.email,
    role: session.role,
    permissions,
    features: {
      anonymousChats: isAnonymousChatsEnabled(),
    },
  });
}
