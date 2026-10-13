import { ApplicationStatus } from '../services/applications.service';
import { I18nService } from '../services/i18n.service';

/** Badge tone per pipeline status (jobs list + job detail render the same badge). */
const PIPELINE_BADGES: Record<ApplicationStatus, string> = {
  saved: 'badge-info',
  applied: 'badge-warning',
  interview: 'badge-warning',
  offer: 'badge-success',
  rejected: 'badge-danger',
};

/** CSS class for a pipeline status badge, defaulting to the neutral tone. */
export function pipelineBadgeClass(status: string): string {
  return PIPELINE_BADGES[status as ApplicationStatus] ?? 'badge-info';
}

/**
 * Localised label for a pipeline status. Unknown statuses (e.g. one added by a
 * newer backend) fall back to "In pipeline" instead of leaking the raw key.
 */
export function pipelineLabelFor(i18n: I18nService, status: string): string {
  const key = `pipeline.${status}`;
  const label = i18n.t(key);
  return label === key ? i18n.t('pipeline.inPipeline') : label;
}
