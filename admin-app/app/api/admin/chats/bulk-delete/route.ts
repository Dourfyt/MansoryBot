import { NextRequest, NextResponse } from 'next/server';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';
import { assertAdmin } from '@/lib/api-guard';
import { purgeTelegramChat } from '@/lib/purge-telegram-chat';

export async function POST(request: NextRequest) {
  const denied = await assertAdmin(request);
  if (denied) return denied;

  const session = await getSessionFromRequest(request);
  const crmUserId = session ? parseInt(session.sub, 10) : null;

  try {
    const body = await request.json();
    const raw = body.chat_ids;
    if (!Array.isArray(raw) || raw.length === 0) {
      return NextResponse.json({ error: 'Нужен непустой массив chat_ids' }, { status: 400 });
    }
    const ids = [...new Set(raw.map((x: unknown) => Number(x)).filter((n) => Number.isFinite(n) && n !== 0))];
    if (ids.length === 0) {
      return NextResponse.json({ error: 'Некорректные chat_ids' }, { status: 400 });
    }

    const errors: { chat_id: number; error: string }[] = [];
    for (const chatId of ids) {
      try {
        await purgeTelegramChat(chatId);
        if (Number.isFinite(crmUserId)) {
          await appendAudit(crmUserId!, 'purge_telegram_chat_bulk', String(chatId));
        }
      } catch (e) {
        errors.push({
          chat_id: chatId,
          error: e instanceof Error ? e.message : 'Ошибка',
        });
      }
    }

    return NextResponse.json({
      ok: true,
      deleted: ids.length - errors.length,
      failed: errors.length,
      errors,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Ошибка';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
