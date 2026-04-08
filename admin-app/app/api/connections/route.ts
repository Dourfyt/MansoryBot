import { NextRequest, NextResponse } from 'next/server';
import { getAllConnections, addConnection, removeConnection, restoreConnection, deleteConnectionPermanently } from '@/lib/database';
import { assertAdminOrSupportPermission } from '@/lib/api-guard';

// Получить все связи
export async function GET(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;
    
    const url = new URL(request.url);
    const inactive = url.searchParams.get('inactive') === 'true';
    
    const connections = await getAllConnections(inactive);
    return NextResponse.json(connections);
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при получении связей' }, { status: 500 });
  }
}

// Добавить новую связь
export async function POST(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;
    
    const body = await request.json();
    const { client_group_id, verifier_group_id } = body;

    if (!client_group_id || !verifier_group_id) {
      return NextResponse.json({ error: 'Необходимы ID групп клиентов и проверяющих' }, { status: 400 });
    }

    const success = await addConnection(client_group_id, verifier_group_id);
    
    if (success) {
      return NextResponse.json({ message: 'Связь успешно добавлена' });
    } else {
      return NextResponse.json({ error: 'Ошибка при добавлении связи' }, { status: 500 });
    }
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при обработке запроса' }, { status: 500 });
  }
}

// Полностью удалить связь
export async function DELETE(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;
    
    const body = await request.json();
    const { client_group_id, verifier_group_id } = body;

    if (!client_group_id || !verifier_group_id) {
      return NextResponse.json({ error: 'Необходимы ID групп клиентов и проверяющих' }, { status: 400 });
    }

    console.log(`Полное удаление связи: client_group_id=${client_group_id}, verifier_group_id=${verifier_group_id}`);
    
    const success = await deleteConnectionPermanently(client_group_id, verifier_group_id);
    
    console.log(`Результат полного удаления: ${success}`);
    
    if (success) {
      return NextResponse.json({ message: 'Связь полностью удалена' });
    } else {
      return NextResponse.json({ error: 'Связь не найдена' }, { status: 404 });
    }
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при обработке запроса' }, { status: 500 });
  }
}

// Деактивировать связь
export async function PUT(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;
    
    const body = await request.json();
    const { client_group_id, verifier_group_id } = body;

    if (!client_group_id || !verifier_group_id) {
      return NextResponse.json({ error: 'Необходимы ID групп клиентов и проверяющих' }, { status: 400 });
    }

    console.log(`Деактивация связи: client_group_id=${client_group_id}, verifier_group_id=${verifier_group_id}`);
    
    const success = await removeConnection(client_group_id, verifier_group_id);
    
    console.log(`Результат деактивации: ${success}`);
    
    if (success) {
      return NextResponse.json({ message: 'Связь деактивирована' });
    } else {
      return NextResponse.json({ error: 'Связь не найдена' }, { status: 404 });
    }
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при обработке запроса' }, { status: 500 });
  }
}

// Восстановить связь
export async function PATCH(request: NextRequest) {
  try {
    const denied = await assertAdminOrSupportPermission(request, 'connections');
    if (denied) return denied;
    
    const body = await request.json();
    const { client_group_id, verifier_group_id } = body;

    if (!client_group_id || !verifier_group_id) {
      return NextResponse.json({ error: 'Необходимы ID групп клиентов и проверяющих' }, { status: 400 });
    }

    const success = await restoreConnection(client_group_id, verifier_group_id);
    
    if (success) {
      return NextResponse.json({ message: 'Связь успешно восстановлена' });
    } else {
      return NextResponse.json({ error: 'Связь не найдена' }, { status: 404 });
    }
  } catch (error) {
    return NextResponse.json({ error: 'Ошибка при обработке запроса' }, { status: 500 });
  }
}
