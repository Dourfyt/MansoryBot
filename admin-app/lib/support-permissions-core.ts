/** Права саппорта в панели (admin всегда имеет всё). Без импорта БД — можно использовать в клиентских компонентах. */
export type SupportPermissions = {
  connections: boolean;
  wallet: boolean;
  broadcast: boolean;
  welcome: boolean;
  anonymous: boolean;
};

export const SUPPORT_PERMISSION_KEYS: (keyof SupportPermissions)[] = [
  'connections',
  'wallet',
  'broadcast',
  'welcome',
  'anonymous',
];

export const DEFAULT_SUPPORT_PERMISSIONS: SupportPermissions = {
  connections: false,
  wallet: false,
  broadcast: false,
  welcome: false,
  anonymous: false,
};

const ALL_TRUE: SupportPermissions = {
  connections: true,
  wallet: true,
  broadcast: true,
  welcome: true,
  anonymous: true,
};

/**
 * NULL в БД — старые записи support: полный доступ (обратная совместимость).
 * Пустой объект {} — явно «ни одного права».
 */
export function parsePermissions(raw: unknown | null | undefined): SupportPermissions {
  if (raw === null || raw === undefined) {
    return { ...ALL_TRUE };
  }
  if (typeof raw !== 'object' || raw === null) {
    return { ...DEFAULT_SUPPORT_PERMISSIONS };
  }
  const o = raw as Record<string, unknown>;
  const empty = Object.keys(o).length === 0;
  if (empty) {
    return { ...DEFAULT_SUPPORT_PERMISSIONS };
  }
  return {
    connections: Boolean(o.connections),
    wallet: Boolean(o.wallet),
    broadcast: Boolean(o.broadcast),
    welcome: Boolean(o.welcome),
    anonymous: Boolean(o.anonymous),
  };
}

export function normalizePermissionsInput(body: unknown): SupportPermissions {
  if (!body || typeof body !== 'object') {
    return { ...DEFAULT_SUPPORT_PERMISSIONS };
  }
  const o = body as Record<string, unknown>;
  return {
    connections: Boolean(o.connections),
    wallet: Boolean(o.wallet),
    broadcast: Boolean(o.broadcast),
    welcome: Boolean(o.welcome),
    anonymous: Boolean(o.anonymous),
  };
}
