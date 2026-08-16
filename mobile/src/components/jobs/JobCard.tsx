import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Badge, BadgeVariant } from '@/components/ui/Badge';
import { Icon } from '@/components/icons/Icon';
import { useI18n } from '@/i18n/I18nProvider';
import { ApplicationStatus, JobSummary } from '@/types';
import { dateLocale, mediumDate } from '@/utils/dates';
import { useTheme } from '@/theme/ThemeProvider';

const PIPELINE_BADGES: Record<ApplicationStatus, BadgeVariant> = {
  saved: 'info',
  applied: 'warning',
  interview: 'warning',
  offer: 'success',
  rejected: 'danger',
};

/** Job card — mirrors the web `.job-card` (title, badges, company, date, tags). */
export function JobCard({
  job,
  pipelineStatus,
  onOpen,
  onToggleHidden,
}: {
  job: JobSummary;
  pipelineStatus?: ApplicationStatus;
  onOpen: () => void;
  onToggleHidden: () => void;
}) {
  const { theme } = useTheme();
  const i18n = useI18n();

  const pipelineLabel = (status: ApplicationStatus): string => {
    const key = `pipeline.${status}`;
    const label = i18n.t(key);
    return label === key ? i18n.t('pipeline.inPipeline') : label;
  };

  return (
    <Pressable
      onPress={onOpen}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: theme.colors.surface,
          borderColor: theme.colors.border,
          opacity: pressed ? 0.9 : 1,
        },
        job.hidden ? { opacity: 0.55 } : null,
      ]}
    >
      <View style={styles.head}>
        <View style={styles.titleRow}>
          <Text style={[styles.title, { color: theme.colors.text }]} numberOfLines={2}>
            {job.title}
          </Text>
          <Pressable onPress={onToggleHidden} hitSlop={10} accessibilityRole="button">
            <Icon
              name={job.hidden ? 'eye' : 'eye-off'}
              size={16}
              color={theme.colors.textFaint}
            />
          </Pressable>
        </View>
        <View style={styles.badges}>
          {pipelineStatus ? (
            <Badge variant={PIPELINE_BADGES[pipelineStatus]}>{pipelineLabel(pipelineStatus)}</Badge>
          ) : null}
          {job.hidden ? <Badge variant="neutral">{i18n.t('jobs.hiddenBadge')}</Badge> : null}
        </View>
      </View>

      <View style={styles.companyRow}>
        <Icon name="home" size={13} color={theme.colors.textMuted} />
        <Text style={[styles.company, { color: theme.colors.textSecondary }]} numberOfLines={1}>
          {job.company}
        </Text>
      </View>

      {job.posted_date ? (
        <View style={styles.dateRow}>
          <Icon name="calendar" size={12} color={theme.colors.textFaint} />
          <Text style={[styles.date, { color: theme.colors.textMuted }]}>
            {i18n.t('jobs.postedPrefix')} {mediumDate(job.posted_date, dateLocale(i18n.lang))}
          </Text>
        </View>
      ) : null}

      {job.tags.length > 0 ? (
        <View style={styles.tags}>
          {job.tags.slice(0, 6).map((tag) => (
            <View key={tag} style={[styles.tag, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
              <Text style={[styles.tagText, { color: theme.colors.textSecondary }]}>{tag}</Text>
            </View>
          ))}
          {job.tags.length > 6 ? (
            <Text style={[styles.tagMore, { color: theme.colors.textFaint }]}>+{job.tags.length - 6}</Text>
          ) : null}
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
    gap: 8,
  },
  head: {
    gap: 6,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  title: {
    flex: 1,
    fontSize: 16,
    fontWeight: '600',
  },
  badges: {
    flexDirection: 'row',
    gap: 6,
    flexWrap: 'wrap',
  },
  companyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  company: {
    fontSize: 14,
    flex: 1,
  },
  dateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  date: {
    fontSize: 12,
  },
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 2,
  },
  tag: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 9999,
    borderWidth: 1,
  },
  tagText: {
    fontSize: 12,
    fontWeight: '500',
  },
  tagMore: {
    fontSize: 12,
    alignSelf: 'center',
  },
});
