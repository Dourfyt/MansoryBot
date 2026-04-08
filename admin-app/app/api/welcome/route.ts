import { NextRequest, NextResponse } from 'next/server';
import { getWelcome, setWelcome, WelcomeLink } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'welcome');
    if (denied) return denied;
    const data = await getWelcome();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Ошибка загрузки приветствия' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'welcome');
    if (denied) return denied;
    const body = await request.json();
    const welcome_message = typeof body.welcome_message === 'string' ? body.welcome_message : '';
    const raw = body.welcome_links;
    const welcome_links: WelcomeLink[] = Array.isArray(raw)
      ? raw
          .filter((x: unknown) => x && typeof x === 'object' && typeof (x as WelcomeLink).url === 'string')
          .map((x: { label?: string; url?: string }) => ({
            label: typeof (x as WelcomeLink).label === 'string' ? (x as WelcomeLink).label : 'Ссылка',
            url: (x as WelcomeLink).url,
          }))
      : [];
    await setWelcome(welcome_message, welcome_links);
    return NextResponse.json({ success: true, message: 'Приветствие и ссылки сохранены' });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Ошибка сохранения' },
      { status: 500 }
    );
  }
}
