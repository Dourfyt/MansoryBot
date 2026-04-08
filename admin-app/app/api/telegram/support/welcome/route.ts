import { NextResponse } from 'next/server';
import { getWelcome } from '@/lib/database';

/** Публичное чтение приветствия и ссылок (как в WelcomeModal) для Mini App поддержки. */
export async function GET() {
  try {
    const data = await getWelcome();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Ошибка загрузки' },
      { status: 500 }
    );
  }
}
