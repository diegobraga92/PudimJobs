import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Switch } from '@/components/ui/Switch';
import { useI18n } from '@/i18n/I18nProvider';
import { useQualityBySource, useQualityJobs, useQualityOverview } from '@/hooks/useAdmin';
import { useTheme } from '@/theme/ThemeProvider';

/** Admin Quality tab — overview metrics, per-source averages and flagged jobs. */
export function QualityTab() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const { data: overview } = useQualityOverview();
  const { data: bySource = [] } = useQualityBySource();
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const { data: jobs = [], error } = useQualityJobs(flaggedOnly);

  return (
    <View style={styles.container}>
      <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('admin.dataQuality')}</Text>
      {overview ? (
        <View style={styles.metrics}>
          <Metric label={i18n.t('admin.statJobs')} value={overview.jobs_total} />
          <Metric label={i18n.t('admin.jobsAssessed')} value={overview.assessed} />
          <Metric label={i18n.t('admin.avgCompleteness')} value={`${Math.round(overview.avg_completeness)}%`} />
          <Metric label={i18n.t('admin.duplicates')} value={overview.duplicates} />
          <Metric label={i18n.t('admin.normalization')} value={`${Math.round(overview.normalization_coverage)}%`} />
          <Metric label={i18n.t('admin.withIssues')} value={overview.jobs_with_issues} />
        </View>
      ) : null}

      {bySource.length > 0 ? (
        <View style={styles.bySource}>
          <Text style={[styles.subTitle, { color: theme.colors.text }]}>{i18n.t('admin.sourceCol')}</Text>
          {bySource.map((item) => (
            <View key={item.source} style={[styles.row, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
              <Text style={[styles.rowLabel, { color: theme.colors.text }]}>{item.source}</Text>
              <Text style={[styles.rowValue, { color: theme.colors.textMuted }]}>
                {item.jobs} · {i18n.t('admin.avgCompleteness')} {Math.round(item.avg_completeness)}%
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.flaggedToggle}>
        <Text style={[styles.toggleLabel, { color: theme.colors.text }]}>{i18n.t('admin.flaggedOnly')}</Text>
        <Switch value={flaggedOnly} onValueChange={setFlaggedOnly} />
      </View>

      {error ? <Alert tone="error">{i18n.t('errors.failedLoadQualityJobs')}</Alert> : null}

      {jobs.length === 0 ? (
        <Text style={[styles.empty, { color: theme.colors.textMuted }]}>{i18n.t('admin.noAssessedJobs')}</Text>
      ) : (
        jobs.map((job) => (
          <View key={job.job_id} style={[styles.jobCard, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
            <View style={styles.jobHead}>
              <Text style={[styles.jobTitle, { color: theme.colors.text }]} numberOfLines={1}>{job.title}</Text>
              {job.is_duplicate ? <Badge variant="danger">{i18n.t('admin.duplicates')}</Badge> : null}
            </View>
            <Text style={[styles.jobMeta, { color: theme.colors.textMuted }]}>
              {job.company} · {i18n.t('admin.completeness')}: {Math.round(job.completeness_score)}%
            </Text>
            {job.issues.length > 0 ? (
              <Text style={[styles.issues, { color: theme.colors.warning }]}>
                {i18n.t('admin.issues')}: {job.issues.join(', ')}
              </Text>
            ) : null}
          </View>
        ))
      )}
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  const { theme } = useTheme();
  return (
    <View style={[styles.metric, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
      <Text style={[styles.metricValue, { color: theme.colors.text }]}>{value}</Text>
      <Text style={[styles.metricLabel, { color: theme.colors.textMuted }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 12,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  subTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  metrics: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  metric: {
    width: '30%',
    flexGrow: 1,
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    gap: 4,
  },
  metricValue: {
    fontSize: 18,
    fontWeight: '700',
  },
  metricLabel: {
    fontSize: 12,
  },
  bySource: {
    gap: 8,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    gap: 8,
  },
  rowLabel: {
    fontSize: 14,
    fontWeight: '600',
    flex: 1,
  },
  rowValue: {
    fontSize: 13,
  },
  flaggedToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  toggleLabel: {
    fontSize: 14,
  },
  empty: {
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 12,
  },
  jobCard: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    gap: 4,
  },
  jobHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  jobTitle: {
    fontSize: 14,
    fontWeight: '600',
    flex: 1,
  },
  jobMeta: {
    fontSize: 13,
  },
  issues: {
    fontSize: 12,
  },
});
