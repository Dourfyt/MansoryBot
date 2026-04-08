import { NextRequest, NextResponse } from 'next/server';
import { bulkRestoreConnections, bulkDeactivateConnections, bulkDeleteConnections } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

/** BIGINT из pg/node-pg приходит строкой; с клиента могут быть number или string. */
function parseGroupId(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === 'string') {
    const t = value.trim();
    if (/^-?\d+$/.test(t)) {
      const n = Number(t);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;

    const body = await request.json();
    const action = body.action; // 'restore' | 'delete' | 'deactivate'
    const connections = Array.isArray(body.connections) ? body.connections : [];

    if (action !== 'restore' && action !== 'delete' && action !== 'deactivate') {
      return NextResponse.json({ error: 'Укажите action: restore, delete или deactivate' }, { status: 400 });
    }

    const items: { client_group_id: number; verifier_group_id: number }[] = [];
    for (const c of connections) {
      if (!c || typeof c !== 'object') continue;
      const o = c as { client_group_id?: unknown; verifier_group_id?: unknown };
      const client_group_id = parseGroupId(o.client_group_id);
      const verifier_group_id = parseGroupId(o.verifier_group_id);
      if (client_group_id !== null && verifier_group_id !== null) {
        items.push({ client_group_id, verifier_group_id });
      }
    }

    if (items.length === 0) {
      return NextResponse.json({ error: 'Нет выбранных связей' }, { status: 400 });
    }

    if (action === 'restore') {
      const { restored } = await bulkRestoreConnections(items);
      return NextResponse.json({
        message: `Восстановлено связей: ${restored} из ${items.length}`,
        restored,
        total: items.length,
      });
    }
    if (action === 'deactivate') {
      const { deactivated } = await bulkDeactivateConnections(items);
      return NextResponse.json({
        message: `Деактивировано связей: ${deactivated} из ${items.length}`,
        deactivated,
        total: items.length,
      });
    }
    const { deleted } = await bulkDeleteConnections(items);
    return NextResponse.json({
      message: `Удалено связей: ${deleted} из ${items.length}`,
      deleted,
      total: items.length,
    });
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при массовой операции' }, { status: 500 });
  }
}
