import { StyleSheet, Text, View } from 'react-native';

import { Skeleton } from '@/components/ui/Skeleton';
import { useAdminStats } from '@/hooks/useAdmin';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';

/** Admin Overview tab — stat cards mirroring the web overview panel. */
export function OverviewTab() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const { data: stats, isPending } = useAdminStats();

  if (isPending) {
    return (
      <View style={styles.grid}>
        {[1, 2, 3, 4].map((item) => (
          <View
            key={item}
            style={[
              styles.card,
              { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
            ]}
          >
            <Skeleton width="40%" height={22} />
            <Skeleton width="70%" height={13} style={{ marginTop: 8 }} />
          </View>
        ))}
      </View>
    );
  }

  if (!stats) {
    return null;
  }

  return (
    <View style={styles.grid}>
      <StatCard label={i18n.t('admin.statSources')} value={stats.sources} />
      <StatCard label={i18n.t('admin.statJobs')} value={stats.jobs} />
      <StatCard label={i18n.t('admin.statJobs24h')} value={stats.jobs_last_24h} />
      <StatCard
        label={i18n.t('admin.statFailedRuns')}
        value={stats.failed_runs}
        alert={stats.failed_runs > 0}
      />
      <StatCard label={i18n.t('admin.statTotalRuns')} value={stats.total_runs} />
    </View>
  );
}

function StatCard({
  label,
  value,
  alert = false,
}: {
  label: string;
  value: number;
  alert?: boolean;
}) {
  const { theme } = useTheme();
  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: theme.colors.surface,
          borderColor: alert ? theme.colors.danger : theme.colors.border,
        },
      ]}
    >
      <Text style={[styles.value, { color: alert ? theme.colors.danger : theme.colors.text }]}>
        {value}
      </Text>
      <Text style={[styles.label, { color: theme.colors.textMuted }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  card: {
    width: '47%',
    flexGrow: 1,
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
    gap: 6,
  },
  value: {
    fontSize: 24,
    fontWeight: '700',
  },
  label: {
    fontSize: 13,
  },
});
