import { describe, it, expect } from 'vitest';
import { hashPassword, verifyPassword } from './auth';

describe('password hashing', () => {
  it('roundtrips verify', async () => {
    const h = await hashPassword('secret-password-123');
    expect(await verifyPassword(h, 'secret-password-123')).toBe(true);
    expect(await verifyPassword(h, 'wrong')).toBe(false);
  });
});
