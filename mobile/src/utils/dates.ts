/** Date helpers mirroring the Angular `date` pipe usages in the web UI: - `mediumDate` (e.g. */
import type { Language } from '@/i18n/I18nProvider';

export type DateLocale = 'en-US' | 'pt-BR';

export function dateLocale(lang: Language): DateLocale {
  return lang === 'pt-BR' ? 'pt-BR' : 'en-US';
}

const formatters = new Map<string, Intl.DateTimeFormat>();

function getFormatter(
  locale: DateLocale,
  options: Intl.DateTimeFormatOptions,
): Intl.DateTimeFormat {
  const key = `${locale}|${JSON.stringify(options)}`;
  let formatter = formatters.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, options);
    formatters.set(key, formatter);
  }
  return formatter;
}

function toDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  // Date-only strings (e.g. posted_date "2026-08-16") must not shift a day
  // when the device is west of UTC — parse the parts into a local Date.
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly) {
    return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Angular `mediumDate` pipe. */
export function mediumDate(value: string | null | undefined, locale: DateLocale = 'en-US'): string {
  const date = toDate(value);
  if (!date) {
    return '';
  }
  return getFormatter(locale, { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
}

/** Angular `short` pipe. */
export function shortDate(value: string | null | undefined, locale: DateLocale = 'en-US'): string {
  const date = toDate(value);
  if (!date) {
    return '';
  }
  return getFormatter(locale, {
    month: 'numeric',
    day: 'numeric',
    year: '2-digit',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

/** CV preview date formatter. Accepts "YYYY", "YYYY-MM" or full ISO dates and renders the short month name + year (mirrors CvPreviewComponent.formatDates). */
export function formatMonthYear(
  value: string | null | undefined,
  locale: DateLocale = 'en-US',
): string {
  if (!value) {
    return '—';
  }
  const match = /^(\d{4})(?:-(\d{1,2}))?/.exec(value.trim());
  if (!match) {
    return value;
  }
  const year = match[1];
  const month = match[2];
  if (!month) {
    return year;
  }
  const idx = Number(month);
  if (idx < 1 || idx > 12) {
    return value;
  }
  return getFormatter(locale, { month: 'short', year: 'numeric' }).format(
    new Date(Number(year), idx - 1, 1),
  );
}

/**
 * Whole days from `now` until `value`, rounded up: `0` means "later today", a
 * positive number is "in N days" and a negative one "N days ago". Returns
 * `null` for a missing/unparsable value. Mirrors the web `dueText` helper.
 */
export function daysUntil(value: string | null | undefined, now: Date = new Date()): number | null {
  const date = toDate(value);
  if (!date) {
    return null;
  }
  // `+ 0` turns the `-0` of an already-past due date into `0`.
  return Math.ceil((date.getTime() - now.getTime()) / 86_400_000) + 0;
}

/** CV preview "start — end" range formatter. */
export function formatDateRange(
  start: string | null,
  end: string | null,
  locale: DateLocale = 'en-US',
): string {
  if (!start && !end) {
    return '—';
  }
  if (start && end) {
    return `${formatMonthYear(start, locale)} — ${formatMonthYear(end, locale)}`;
  }
  return formatMonthYear(start || end || '', locale);
}
