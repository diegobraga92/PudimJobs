import { StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Icon } from '@/components/icons/Icon';
import { useToast } from '@/components/toast/ToastProvider';
import { useSourceHealth, useTriggerScrape } from '@/hooks/useAdmin';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { dateLocale, shortDate } from '@/utils/dates';

/** Admin Sources tab — source health with manual scrape triggers. */
export function SourcesTab() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const { data: sources = [], error } = useSourceHealth();
  const triggerScrape = useTriggerScrape();

  const scrape = (sourceId: string) => {
    triggerScrape.mutate(sourceId, {
      onSuccess: () => toast.success(i18n.t('admin.scrapeTriggered')),
      onError: () => toast.error(i18n.t('errors.failedTriggerScrape')),
    });
  };

  if (error) {
    return <Alert tone="error">{i18n.t('errors.failedLoadSourceHealth')}</Alert>;
  }

  if (sources.length === 0) {
    return (
      <EmptyState
        icon="globe"
        title={i18n.t('sources.noSourcesYet')}
        hint={i18n.t('sources.noSourcesHint')}
      />
    );
  }

  return (
    <View style={styles.list}>
      <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>
        {i18n.t('admin.sourceHealth')}
      </Text>
      {sources.map((source) => (
        <View
          key={source.id}
          style={[
            styles.row,
            { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
          ]}
        >
          <View style={styles.info}>
            <Text style={[styles.name, { color: theme.colors.text }]}>{source.name}</Text>
            <Text style={[styles.meta, { color: theme.colors.textMuted }]}>
              {source.type} · {i18n.t('admin.lastScraped')}:{' '}
              {source.last_scraped
                ? shortDate(source.last_scraped, dateLocale(i18n.lang))
                : i18n.t('admin.never')}
            </Text>
          </View>
          <Badge
            variant={
              source.health === 'healthy'
                ? 'success'
                : source.health === 'failing'
                  ? 'danger'
                  : 'warning'
            }
          >
            {source.health}
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            onPress={() => scrape(source.id)}
            loading={triggerScrape.isPending}
          >
            <Icon name="refresh" size={14} />
            {i18n.t('admin.scrapeNow')}
          </Button>
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
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
  },
  info: {
    flex: 1,
    gap: 2,
  },
  name: {
    fontSize: 14,
    fontWeight: '600',
  },
  meta: {
    fontSize: 12,
  },
});
