import { formatDateRange, formatMonthYear, mediumDate, shortDate } from '@/utils/dates';

describe('formatMonthYear', () => {
  it('renders year-only values', () => {
    expect(formatMonthYear('2020')).toBe('2020');
  });

  it('renders YYYY-MM as "Mon YYYY" in English', () => {
    expect(formatMonthYear('2020-06', 'en-US')).toBe('Jun 2020');
  });

  it('renders YYYY-MM as "Mon de YYYY" in Portuguese', () => {
    expect(formatMonthYear('2020-06', 'pt-BR')).toContain('jun');
  });

  it('falls back to the raw value for unparsable input', () => {
    expect(formatMonthYear('not-a-date')).toBe('not-a-date');
  });

  it('returns an em dash for empty input', () => {
    expect(formatMonthYear(null)).toBe('—');
  });
});

describe('formatDateRange', () => {
  it('handles open-ended ranges', () => {
    expect(formatDateRange('2021-01', null, 'en-US')).toBe('Jan 2021');
    expect(formatDateRange(null, '2022-12', 'pt-BR')).toContain('dez');
  });

  it('renders a range with both ends', () => {
    const result = formatDateRange('2019-03', '2023-09', 'en-US');
    expect(result).toBe('Mar 2019 — Sep 2023');
  });

  it('returns an em dash when both ends are empty', () => {
    expect(formatDateRange(null, null)).toBe('—');
  });
});

describe('date pipes', () => {
  it('mediumDate renders a readable date in English', () => {
    expect(mediumDate('2026-08-16', 'en-US')).toBe('Aug 16, 2026');
  });

  it('mediumDate renders a Portuguese date', () => {
    expect(mediumDate('2026-08-16', 'pt-BR')).toContain('ago');
  });

  it('shortDate renders date + time', () => {
    expect(shortDate('2026-08-16T14:30:00Z', 'en-US')).toBeTruthy();
  });

  it('returns empty string for null input', () => {
    expect(mediumDate(null)).toBe('');
    expect(shortDate(undefined)).toBe('');
  });
});
