import { NextRequest, NextResponse } from 'next/server';
import { testConnection } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;

    const body = await request.json();
    const { client_group_id, verifier_group_id } = body;

    if (!client_group_id || !verifier_group_id) {
      return NextResponse.json({ error: 'Необходимы ID групп клиентов и проверяющих' }, { status: 400 });
    }

    const result = await testConnection(client_group_id, verifier_group_id);

    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при обработке запроса' }, { status: 500 });
  }
}
