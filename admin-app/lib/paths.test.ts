import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { getDatabasePath } from './paths';

describe('getDatabasePath', () => {
  const orig = process.env.DATABASE_URL;

  afterEach(() => {
    if (orig === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = orig;
    }
  });

  it('returns DATABASE_URL when set', () => {
    process.env.DATABASE_URL = 'postgresql://u:p@localhost:5432/db';
    expect(getDatabasePath()).toBe('postgresql://u:p@localhost:5432/db');
  });
});
