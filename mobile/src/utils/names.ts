/**
 * Best-effort display name derived from an account email — the app has no
 * dedicated "full name" field, so `jane.doe@example.com` becomes "Jane Doe".
 */
export function displayNameFromEmail(email: string | undefined): string {
  if (!email) {
    return 'Your Name';
  }
  const local = email.split('@')[0] || '';
  return (
    local
      .split(/[._-]/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ') || 'Your Name'
  );
}
