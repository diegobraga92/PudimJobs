import { displayNameFromEmail } from '@/utils/names';

describe('displayNameFromEmail', () => {
  it('title-cases the local part, splitting on . _ -', () => {
    expect(displayNameFromEmail('jane.doe@example.com')).toBe('Jane Doe');
    expect(displayNameFromEmail('jane_doe@example.com')).toBe('Jane Doe');
    expect(displayNameFromEmail('jane-doe@example.com')).toBe('Jane Doe');
  });

  it('falls back when there is no usable local part', () => {
    expect(displayNameFromEmail(undefined)).toBe('Your Name');
    expect(displayNameFromEmail('')).toBe('Your Name');
    expect(displayNameFromEmail('@example.com')).toBe('Your Name');
  });
});
