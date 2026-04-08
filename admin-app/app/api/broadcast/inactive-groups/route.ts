import { NextRequest, NextResponse } from 'next/server';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

const BOT_BROADCAST_URL = process.env.BOT_BROADCAST_URL || 'http://127.0.0.1:8765';

function botHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  const secret = process.env.BROADCAST_INTERNAL_SECRET?.trim();
  if (secret) h['X-Internal-Secret'] = secret;
  return h;
}

export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'broadcast');
    if (denied) return denied;

    const res = await fetch(`${BOT_BROADCAST_URL}/broadcast/inactive-groups`, {
      headers: botHeaders(),
    });
    const data = await res.json();
    if (res.ok) {
      return NextResponse.json(data);
    }
    return NextResponse.json({ error: data.error || 'Ошибка запроса к боту' }, { status: res.status });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : 'Бот недоступен. Убедитесь, что бот запущен.',
      },
      { status: 502 }
    );
  }
}
