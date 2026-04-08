import { query } from '@/lib/db';
import {
  type SupportPermissions,
  parsePermissions,
  DEFAULT_SUPPORT_PERMISSIONS,
} from './support-permissions-core';

export type { SupportPermissions };
export {
  SUPPORT_PERMISSION_KEYS,
  DEFAULT_SUPPORT_PERMISSIONS,
  parsePermissions,
  normalizePermissionsInput,
} from './support-permissions-core';

export async function getSupportPermissionsByUserId(userId: number): Promise<SupportPermissions> {
  const { rows } = await query<{ role: string; support_permissions: unknown }>(
    'SELECT role, support_permissions FROM crm_users WHERE id = $1',
    [userId]
  );
  const r = rows[0];
  if (!r) {
    return { ...DEFAULT_SUPPORT_PERMISSIONS };
  }
  if (r.role === 'admin') {
    return {
      connections: true,
      wallet: true,
      broadcast: true,
      welcome: true,
      anonymous: true,
    };
  }
  return parsePermissions(r.support_permissions);
}
