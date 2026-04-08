import { NextRequest, NextResponse } from 'next/server';
import { updateGroupId } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;

    const body = await request.json();
    const { old_group_id, new_group_id } = body;

    if (!old_group_id || !new_group_id) {
      return NextResponse.json({ error: 'Необходимы старый и новый ID группы' }, { status: 400 });
    }

    const success = await updateGroupId(old_group_id, new_group_id);

    if (success) {
      return NextResponse.json({ message: 'ID группы успешно обновлен' });
    } else {
      return NextResponse.json({ error: 'Группа с указанным старым ID не найдена' }, { status: 404 });
    }
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при обработке запроса' }, { status: 500 });
  }
}
