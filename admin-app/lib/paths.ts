/** Раньше: путь к SQLite. Сейчас БД — PostgreSQL, строка подключения в DATABASE_URL. */
export function getDatabasePath(): string {
  return process.env.DATABASE_URL?.trim() || '';
}
