import { NextRequest, NextResponse } from 'next/server';
import { updateGroupNames } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;

    const result = await updateGroupNames();

    return NextResponse.json({
      success: true,
      message: `Обновлено названий: ${result.updated}, ошибок: ${result.errors}`,
      updated: result.updated,
      errors: result.errors,
    });
  } catch (error) {
    console.error('Ошибка при обновлении названий групп:', error);
    return NextResponse.json({ error: 'Ошибка при обновлении названий групп' }, { status: 500 });
  }
}
