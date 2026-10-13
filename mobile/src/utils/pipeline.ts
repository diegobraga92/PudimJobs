import type { BadgeVariant } from '@/components/ui/Badge';
import { ApplicationStatus } from '@/types';

/** Badge tone per pipeline status (job card + job detail render the same badge). */
const PIPELINE_BADGES: Record<ApplicationStatus, BadgeVariant> = {
  saved: 'info',
  applied: 'warning',
  interview: 'warning',
  offer: 'success',
  rejected: 'danger',
};

/** Badge variant for a pipeline status. */
export function pipelineBadgeVariant(status: ApplicationStatus): BadgeVariant {
  return PIPELINE_BADGES[status] ?? 'info';
}

/**
 * Localised label for a pipeline status. Unknown statuses (e.g. one added by a
 * newer backend) fall back to "In pipeline" instead of leaking the raw key.
 */
export function pipelineLabel(status: string, t: (key: string) => string): string {
  const key = `pipeline.${status}`;
  const label = t(key);
  return label === key ? t('pipeline.inPipeline') : label;
}
