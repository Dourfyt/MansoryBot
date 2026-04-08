import { NextRequest, NextResponse } from 'next/server';
import { getConnectionStats } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;

    const stats = await getConnectionStats();
    return NextResponse.json(stats);
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при получении статистики' }, { status: 500 });
  }
}
