import { NextRequest, NextResponse } from 'next/server';
import { getBroadcastGroups } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'broadcast');
    if (denied) return denied;
    const groups = await getBroadcastGroups();
    return NextResponse.json(groups);
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при загрузке списка групп' }, { status: 500 });
  }
}
