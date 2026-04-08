import { NextRequest, NextResponse } from 'next/server';
import { getBroadcastAlwaysExcludeChatIds, getBroadcastGroups } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';
import { resolveBotToken } from '@/lib/resolve-bot-token';

const BOT_BROADCAST_URL = process.env.BOT_BROADCAST_URL || 'http://127.0.0.1:8765';

export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'broadcast');
    if (denied) return denied;

    const body = await request.json();
    const text = typeof body.text === 'string' ? body.text.trim() : '';
    const sessionExclude: number[] = Array.isArray(body.exclude_chat_ids)
      ? body.exclude_chat_ids.filter((id: unknown) => typeof id === 'number')
      : [];
    const alwaysExclude = await getBroadcastAlwaysExcludeChatIds();
    const excludeChatIds = [...new Set([...sessionExclude, ...alwaysExclude])];

    if (!text) {
      return NextResponse.json({ error: 'Введите текст сообщения' }, { status: 400 });
    }

    const internalSecret = process.env.BROADCAST_INTERNAL_SECRET?.trim();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (internalSecret) {
      headers['X-Internal-Secret'] = internalSecret;
    }

    try {
      const res = await fetch(`${BOT_BROADCAST_URL}/broadcast`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ text, exclude_chat_ids: excludeChatIds }),
      });
      const data = await res.json();
      if (res.ok) {
        return NextResponse.json(data);
      }
      return NextResponse.json({ error: data.error || 'Ошибка рассылки на боте' }, { status: res.status });
    } catch (_) {
      // Бот недоступен — fallback: рассылка через Telegram API (один бот)
    }

    const allGroups = await getBroadcastGroups();
    const toSend = allGroups.filter((g) => !excludeChatIds.includes(g.chat_id));
    if (toSend.length === 0) {
      return NextResponse.json({
        success: true,
        sent: 0,
        failed: 0,
        message: 'Нет групп для рассылки (все исключены или список пуст)',
      });
    }

    const token = await resolveBotToken();
    const url = `https://api.telegram.org/bot${token}/sendMessage`;
    let sent = 0;
    const errors: { chat_id: number; error: string }[] = [];
    for (const group of toSend) {
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: group.chat_id,
            text,
            parse_mode: 'HTML',
            disable_web_page_preview: true,
          }),
        });
        const data = await res.json();
        if (data.ok) sent++;
        else errors.push({ chat_id: group.chat_id, error: data.description || 'Unknown error' });
      } catch (err) {
        errors.push({ chat_id: group.chat_id, error: err instanceof Error ? err.message : 'Request failed' });
      }
    }
    return NextResponse.json({
      success: true,
      sent,
      failed: errors.length,
      total: toSend.length,
      errors: errors.length > 0 ? errors : undefined,
      message: `Отправлено: ${sent} из ${toSend.length}${errors.length > 0 ? `. Ошибки: ${errors.length}` : ''}`,
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Ошибка при рассылке' },
      { status: 500 }
    );
  }
}
