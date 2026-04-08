import { Pool } from 'pg';

let pool: Pool | null = null;

export function getPool(): Pool {
  if (!pool) {
    const url = process.env.DATABASE_URL?.trim();
    if (!url) {
      throw new Error('DATABASE_URL is required (PostgreSQL connection string)');
    }
    pool = new Pool({ connectionString: url });
  }
  return pool;
}

export async function query<T = unknown>(
  text: string,
  params?: unknown[]
): Promise<{ rows: T[]; rowCount: number }> {
  const res = await getPool().query(text, params);
  return { rows: res.rows as T[], rowCount: res.rowCount ?? 0 };
}

/** Транзакция: client.query + COMMIT/ROLLBACK внутри callback */
export async function withTransaction<T>(fn: (client: import('pg').PoolClient) => Promise<T>): Promise<T> {
  const pool = getPool();
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const out = await fn(client);
    await client.query('COMMIT');
    return out;
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
  }
}
