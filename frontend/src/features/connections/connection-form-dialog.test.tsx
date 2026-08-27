import { describe, expect, it } from 'vitest';
import { buildCredential } from './connection-form-dialog';

describe('buildCredential', () => {
  it('requires a non-empty access token', () => {
    expect(buildCredential('')).toBeNull();
    expect(buildCredential('   ')).toBeNull();
  });

  it('trims the access token', () => {
    expect(buildCredential('  ghp_token  ')).toEqual({ accessToken: 'ghp_token' });
  });
});
