import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'wallet');
    if (denied) return denied;

    const { rows } = await query<{ wallet_address: string | null }>(
      'SELECT wallet_address FROM global_settings WHERE id = 1'
    );

    return NextResponse.json({
      wallet_address: rows[0]?.wallet_address ?? null,
    });
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'Ошибка при получении адреса кошелька';
    console.error('Ошибка при получении адреса кошелька:', error);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'wallet');
    if (denied) return denied;

    const body = await request.json();
    const { wallet_address } = body;

    await query(
      `INSERT INTO global_settings (id, wallet_address, updated_at)
       VALUES (1, $1, CURRENT_TIMESTAMP)
       ON CONFLICT (id) DO UPDATE SET
         wallet_address = EXCLUDED.wallet_address,
         updated_at = CURRENT_TIMESTAMP`,
      [wallet_address || null]
    );

    return NextResponse.json({
      success: true,
      message: 'Адрес кошелька успешно обновлен',
    });
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'Ошибка при обновлении адреса кошелька';
    console.error('Ошибка при обновлении адреса кошелька:', error);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
