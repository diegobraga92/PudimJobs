import { StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Icon } from '@/components/icons/Icon';
import { useToast } from '@/components/toast/ToastProvider';
import { useDlq, useReplayRun } from '@/hooks/useAdmin';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { shortDate } from '@/utils/dates';

/** Admin DLQ tab — failed scrape runs with replay. */
export function DlqTab() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const { data: runs = [], error } = useDlq();
  const replay = useReplayRun();

  if (error) {
    return <Alert tone="error">{i18n.t('errors.failedLoadDlq')}</Alert>;
  }

  if (runs.length === 0) {
    return (
      <EmptyState
        icon="circle-alert"
        title={i18n.t('admin.dlqTitle')}
        hint={i18n.t('admin.noFailedRuns')}
      />
    );
  }

  const onReplay = (runId: string) => {
    replay.mutate(runId, {
      onSuccess: () => toast.success(i18n.t('admin.runReplayed')),
      onError: () => toast.error(i18n.t('errors.failedReplay')),
    });
  };

  return (
    <View style={styles.list}>
      <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('admin.dlqTitle')}</Text>
      {runs.map((run) => (
        <View key={run.id} style={[styles.runCard, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
          <View style={styles.runHead}>
            <Text style={[styles.runId, { color: theme.colors.text }]} numberOfLines={1}>
              {run.source_id}
            </Text>
            <Badge variant={run.status === 'failed' ? 'danger' : 'warning'}>{run.status}</Badge>
          </View>
          <Text style={[styles.meta, { color: theme.colors.textMuted }]}>
            {i18n.t('admin.started')}: {shortDate(run.started_at)}
            {run.finished_at ? ` · ${shortDate(run.finished_at)}` : ''}
          </Text>
          {run.error ? <Text style={[styles.error, { color: theme.colors.danger }]} numberOfLines={2}>{run.error}</Text> : null}
          <View style={styles.actions}>
            <Button variant="ghost" size="sm" onPress={() => onReplay(run.id)} loading={replay.isPending}>
              <Icon name="refresh" size={14} />
              {i18n.t('admin.replay')}
            </Button>
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: 10,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 2,
  },
  runCard: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    gap: 6,
  },
  runHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  runId: {
    fontSize: 14,
    fontWeight: '600',
    flex: 1,
  },
  meta: {
    fontSize: 12,
  },
  error: {
    fontSize: 12,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
});
