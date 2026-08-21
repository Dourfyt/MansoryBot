import { NextResponse } from 'next/server';

/** Анонимные чаты включены только при явном ANONYMOUS_CHATS_ENABLED=true (или NEXT_PUBLIC_*). */
export function isAnonymousChatsEnabled(): boolean {
  const raw = (
    process.env.ANONYMOUS_CHATS_ENABLED ??
    process.env.NEXT_PUBLIC_ANONYMOUS_CHATS_ENABLED ??
    'false'
  )
    .trim()
    .toLowerCase();
  return raw === '1' || raw === 'true' || raw === 'yes' || raw === 'on';
}

/** Фича выключена: для мутаций — 404 без тела (как несуществующий endpoint). */
export function anonymousChatsDisabledResponse(): NextResponse {
  return new NextResponse(null, { status: 404 });
}

/** Фича выключена: для GET — пустой ответ в ожидаемой форме (без ошибки). */
export function anonymousChatsEmptyGetResponse(
  payload: Record<string, unknown>,
): NextResponse | null {
  if (!isAnonymousChatsEnabled()) {
    return NextResponse.json(payload);
  }
  return null;
}
