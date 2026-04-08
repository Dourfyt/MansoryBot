import { NextRequest, NextResponse } from 'next/server';
import { appendAudit, getSessionFromRequest } from '@/lib/auth';
import { assertAdmin } from '@/lib/api-guard';
import { purgeTelegramChat } from '@/lib/purge-telegram-chat';

export async function DELETE(
  request: NextRequest,
  context: { params: { chatId: string } }
) {
  const denied = await assertAdmin(request);
  if (denied) return denied;

  const session = await getSessionFromRequest(request);
  const crmUserId = session ? parseInt(session.sub, 10) : null;

  const chatId = parseInt(context.params.chatId, 10);
  if (!Number.isFinite(chatId) || chatId === 0) {
    return NextResponse.json({ error: 'Некорректный chat_id' }, { status: 400 });
  }

  try {
    await purgeTelegramChat(chatId);
    if (Number.isFinite(crmUserId)) {
      await appendAudit(crmUserId, 'purge_telegram_chat', String(chatId));
    }
    return NextResponse.json({ ok: true });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Ошибка удаления';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
