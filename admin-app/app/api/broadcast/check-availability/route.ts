import { NextRequest, NextResponse } from 'next/server';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

const BOT_BROADCAST_URL = process.env.BOT_BROADCAST_URL || 'http://127.0.0.1:8765';

function botHeaders(): HeadersInit {
  const secret = process.env.BROADCAST_INTERNAL_SECRET?.trim();
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (secret) h['X-Internal-Secret'] = secret;
  return h;
}

export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'broadcast');
    if (denied) return denied;

    const res = await fetch(`${BOT_BROADCAST_URL}/broadcast/check-availability`, {
      method: 'POST',
      headers: botHeaders(),
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (res.ok) {
      return NextResponse.json(data);
    }
    return NextResponse.json(
      { error: data.error || 'Ошибка проверки доступности на боте' },
      { status: res.status }
    );
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : 'Бот недоступен. Убедитесь, что бот запущен и слушает порт 8765.',
      },
      { status: 502 }
    );
  }
}
