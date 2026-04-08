import { NextRequest, NextResponse } from 'next/server';
import { assertAdmin } from '@/lib/api-guard';

const BOT_BROADCAST_URL = process.env.BOT_BROADCAST_URL || 'http://127.0.0.1:8765';

export const maxDuration = 900;

function botHeaders(): HeadersInit {
  const secret = process.env.BROADCAST_INTERNAL_SECRET?.trim();
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (secret) h['X-Internal-Secret'] = secret;
  return h;
}

/** Создать бессрочные invite-ссылки для указанных чатов (бот должен быть админом). */
export async function POST(request: NextRequest) {
  const denied = await assertAdmin(request);
  if (denied) return denied;

  try {
    const body = await request.json();
    const chat_ids = body.chat_ids;
    if (!Array.isArray(chat_ids) || chat_ids.length === 0) {
      return NextResponse.json({ error: 'Нужен непустой массив chat_ids' }, { status: 400 });
    }
    const res = await fetch(`${BOT_BROADCAST_URL}/broadcast/create-invite-links`, {
      method: 'POST',
      headers: botHeaders(),
      body: JSON.stringify({ chat_ids }),
      signal: AbortSignal.timeout(15 * 60 * 1000),
    });
    const data = await res.json();
    if (res.ok) {
      return NextResponse.json(data);
    }
    return NextResponse.json(
      { error: data.error || 'Ошибка создания ссылок на боте' },
      { status: res.status }
    );
  } catch (error) {
    const name = error instanceof Error ? error.name : '';
    const msg = error instanceof Error ? error.message : String(error);
    if (
      name === 'TimeoutError' ||
      name === 'AbortError' ||
      /aborted|timeout/i.test(msg)
    ) {
      return NextResponse.json(
        {
          error:
            'Превышено время ожидания. Увеличьте proxy_read_timeout у nginx или в панели уже идёт пакетная генерация по 8 чатов — обновите страницу и повторите.',
        },
        { status: 504 }
      );
    }
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : 'Бот недоступен. Проверьте BOT_BROADCAST_URL и запуск бота.',
      },
      { status: 502 }
    );
  }
}
