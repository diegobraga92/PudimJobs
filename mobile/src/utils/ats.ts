import { BadgeVariant } from '@/components/ui/Badge';

/** Badge tone for an ATS score (green ≥ 75, amber ≥ 50, red below). */
export function scoreVariant(score: number): BadgeVariant {
  if (score >= 75) {
    return 'success';
  }
  return score >= 50 ? 'warning' : 'danger';
}

/** 0..1 factor score rendered as a 0..100 bar width. */
export function factorPercent(score: number): number {
  return Math.max(0, Math.min(100, Math.round(score * 100)));
}
