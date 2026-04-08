import { NextRequest, NextResponse } from 'next/server';
import { assertAdmin } from '@/lib/api-guard';

const BOT_BROADCAST_URL = process.env.BOT_BROADCAST_URL || 'http://127.0.0.1:8765';

/** Долгая операция: прокси/nginx по умолчанию часто режут по 60 с — увеличьте proxy_read_timeout у reverse-proxy. */
export const maxDuration = 900;

function botHeaders(): HeadersInit {
  const secret = process.env.BROADCAST_INTERNAL_SECRET?.trim();
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (secret) h['X-Internal-Secret'] = secret;
  return h;
}

const FETCH_MS = 15 * 60 * 1000;

/** Прокси на бот: проверка доступа ко всем переданным chat_id (панель /admin/chats). */
export async function POST(request: NextRequest) {
  const denied = await assertAdmin(request);
  if (denied) return denied;

  try {
    const body = await request.json();
    const chat_ids = body.chat_ids;
    if (!Array.isArray(chat_ids) || chat_ids.length === 0) {
      return NextResponse.json({ error: 'Нужен непустой массив chat_ids' }, { status: 400 });
    }
    const res = await fetch(`${BOT_BROADCAST_URL}/broadcast/check-admin-chats`, {
      method: 'POST',
      headers: botHeaders(),
      body: JSON.stringify({ chat_ids }),
      signal: AbortSignal.timeout(FETCH_MS),
    });
    const data = await res.json();
    if (res.ok) {
      return NextResponse.json(data);
    }
    return NextResponse.json(
      { error: data.error || 'Ошибка проверки на боте' },
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
            'Превышено время ожидания ответа от бота. На сервере увеличьте proxy_read_timeout / fastcgi_read (nginx) или разбейте проверку на меньшие партии.',
        },
        { status: 504 }
      );
    }
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : 'Бот недоступен. Убедитесь, что процесс бота запущен и слушает порт рассылки.',
      },
      { status: 502 }
    );
  }
}
