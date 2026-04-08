import { NextRequest, NextResponse } from 'next/server';
import {
  getBroadcastAlwaysExcludeChatIds,
  setBroadcastAlwaysExcludeChatIds,
} from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'broadcast');
    if (denied) return denied;
    const chat_ids = await getBroadcastAlwaysExcludeChatIds();
    return NextResponse.json({ chat_ids });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Ошибка при загрузке списка' },
      { status: 500 }
    );
  }
}

export async function PUT(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'broadcast');
    if (denied) return denied;
    const body = await request.json();
    const raw = body?.chat_ids;
    if (!Array.isArray(raw)) {
      return NextResponse.json({ error: 'Ожидался массив chat_ids' }, { status: 400 });
    }
    const chat_ids = raw
      .map((id: unknown) => (typeof id === 'number' ? id : Number(id)))
      .filter((id: number) => Number.isFinite(id));
    await setBroadcastAlwaysExcludeChatIds(chat_ids);
    return NextResponse.json({ ok: true, chat_ids });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Ошибка при сохранении' },
      { status: 500 }
    );
  }
}
