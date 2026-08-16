import { RouteProp, useNavigation, useRoute } from '@react-navigation/native';
import { useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { RenderHTML } from 'react-native-render-html';

import { AppHeader } from '@/components/layout/AppHeader';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tag } from '@/components/ui/Tag';
import { Icon } from '@/components/icons/Icon';
import { useConfirm } from '@/components/confirm/ConfirmProvider';
import { useToast } from '@/components/toast/ToastProvider';
import { useCreateApplication } from '@/hooks/useApplications';
import { useJob, useParsedJd, useParseJob, useTailorCv, useUpdateJob, useDeleteJob } from '@/hooks/useJobs';
import { useI18n } from '@/i18n/I18nProvider';
import { JobsStackParamList } from '@/navigation/types';
import { useTheme } from '@/theme/ThemeProvider';
import { dateLocale, mediumDate } from '@/utils/dates';

export function JobDetailScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const navigation = useNavigation();
  const route = useRoute<RouteProp<JobsStackParamList, 'JobDetail'>>();
  const toast = useToast();
  const confirm = useConfirm();
  const { width } = useWindowDimensions();
  const { id } = route.params;

  const { data: job, isPending, error } = useJob(id);
  const parsed = useParsedJd(id, !!job);

  const createApplication = useCreateApplication();
  const updateJob = useUpdateJob(id);
  const deleteJob = useDeleteJob();
  const parseJob = useParseJob();
  const tailor = useTailorCv();

  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const loadError = error ? i18n.t('errors.failedLoadJob') : null;
  const displayError = loadError ?? actionError;

  const back = () => navigation.goBack();

  const addApplication = () => {
    if (!job) {
      return;
    }
    setMessage(null);
    createApplication.mutate(
      { job_id: job.id, status: 'saved' },
      {
        onSuccess: () => {
          setMessage(i18n.t('jobDetail.addedToPipeline'));
          toast.success(i18n.t('jobDetail.addedToPipeline'));
        },
        onError: () => {
          setMessage(i18n.t('jobDetail.couldNotAdd'));
          toast.error(i18n.t('jobDetail.couldNotAdd'));
        },
      },
    );
  };

  const runTailor = () => {
    if (!job) {
      return;
    }
    setMessage(null);
    tailor.mutate(
      { id: job.id },
      {
        onSuccess: () => {
          setMessage(i18n.t('jobDetail.tailoringStarted'));
          toast.success(i18n.t('jobDetail.tailoringStartedToast'));
        },
        onError: () => {
          setMessage(i18n.t('jobDetail.failedTailoring'));
          toast.error(i18n.t('jobDetail.failedTailoringToast'));
        },
      },
    );
  };

  const toggleHidden = () => {
    if (!job) {
      return;
    }
    const target = !job.hidden;
    setMessage(null);
    updateJob.mutate(
      { hidden: target },
      {
        onSuccess: () => {
          setMessage(target ? i18n.t('jobDetail.hidden') : i18n.t('jobDetail.unhidden'));
          toast.success(target ? i18n.t('jobs.jobHidden') : i18n.t('jobs.jobUnhidden'));
        },
        onError: () => {
          setActionError(i18n.t('errors.failedHideJob'));
          toast.error(i18n.t('errors.failedHideJob'));
        },
      },
    );
  };

  const remove = async () => {
    if (!job) {
      return;
    }
    const confirmed = await confirm.confirm({
      title: i18n.t('jobDetail.deleteTitle'),
      message: i18n.t('jobDetail.deleteMessage', { title: job.title }),
      confirmLabel: i18n.t('common.delete'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    deleteJob.mutate(job.id, {
      onSuccess: () => {
        toast.success(i18n.t('jobDetail.deleted'));
        navigation.goBack();
      },
      onError: () => {
        setActionError(i18n.t('errors.failedDeleteJob'));
        toast.error(i18n.t('errors.failedDeleteJob'));
      },
    });
  };

  const parseNow = () => {
    if (!job) {
      return;
    }
    setMessage(null);
    parseJob.mutate(job.id, {
      onSuccess: () => {
        setMessage(i18n.t('jobDetail.parsingQueued'));
        toast.info(i18n.t('jobDetail.parsingQueuedToast'));
      },
      onError: () => {
        setActionError(i18n.t('errors.failedEnqueueParsing'));
        toast.error(i18n.t('errors.failedEnqueueParsing'));
      },
    });
  };

  const descriptionHtml = job?.description?.trim() ? job.description : null;

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <AppHeader title={job?.title ?? i18n.t('jobs.title')} back onLeftPress={back} />
      <ScrollView contentContainerStyle={styles.content} style={styles.flex}>
        {isPending ? (
          <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
            <Skeleton width="55%" height={22} />
            <Skeleton width="30%" height={14} style={{ marginTop: 12 }} />
            <Skeleton width="40%" height={13} style={{ marginTop: 16 }} />
            <Skeleton width="65%" height={34} style={{ marginTop: 20 }} />
            <Skeleton width="90%" height={13} style={{ marginTop: 20 }} />
            <Skeleton width="85%" height={13} style={{ marginTop: 8 }} />
            <Skeleton width="70%" height={13} style={{ marginTop: 8 }} />
          </View>
        ) : null}

        {!isPending && displayError ? <Alert tone="error">{displayError}</Alert> : null}

        {!isPending && job ? (
          <>
            <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
              <View style={styles.titleRow}>
                <Text style={[styles.title, { color: theme.colors.text }]}>{job.title}</Text>
                {job.hidden ? <Badge variant="neutral">{i18n.t('jobs.hiddenBadge')}</Badge> : null}
              </View>

              <View style={styles.metaRow}>
                <Icon name="home" size={14} color={theme.colors.textMuted} />
                <Text style={[styles.meta, { color: theme.colors.textSecondary }]}>{job.company}</Text>
              </View>

              {job.posted_date ? (
                <View style={styles.metaRow}>
                  <Icon name="calendar" size={13} color={theme.colors.textFaint} />
                  <Text style={[styles.metaMuted, { color: theme.colors.textMuted }]}>
                    {i18n.t('jobs.postedPrefix')} {mediumDate(job.posted_date, dateLocale(i18n.lang))}
                  </Text>
                </View>
              ) : null}

              {job.tags.length > 0 ? (
                <View style={styles.tags}>
                  {job.tags.map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                </View>
              ) : null}

              {job.url ? (
                <Pressable
                  onPress={() => void Linking.openURL(job.url as string)}
                  accessibilityRole="link"
                  style={styles.linkRow}
                >
                  <Text style={[styles.link, { color: theme.colors.accent }]}>
                    {i18n.t('jobDetail.viewOriginal')}
                  </Text>
                  <Icon name="external-link" size={13} color={theme.colors.accent} />
                </Pressable>
              ) : null}

              <View style={styles.actions}>
                <Button onPress={addApplication} loading={createApplication.isPending}>
                  {createApplication.isPending
                    ? i18n.t('jobDetail.adding')
                    : i18n.t('jobDetail.addToApplications')}
                </Button>
                <Button variant="accent" onPress={runTailor} loading={tailor.isPending}>
                  {tailor.isPending ? i18n.t('jobDetail.tailoring') : i18n.t('jobDetail.tailorCv')}
                </Button>
                <Button variant="ghost" onPress={toggleHidden} loading={updateJob.isPending}>
                  {job.hidden ? i18n.t('jobDetail.unhide') : i18n.t('jobDetail.hide')}
                </Button>
                <Button variant="danger" onPress={() => void remove()}>
                  {i18n.t('jobDetail.delete')}
                </Button>
              </View>

              {message ? <Alert tone="success">{message}</Alert> : null}
            </View>



            <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
              <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>
                {i18n.t('jobDetail.parsedRequirements')}
              </Text>
              {parsed.data ? (
                <View style={styles.parsed}>
                  <View style={styles.parsedRow}>
                    <Text style={[styles.parsedLabel, { color: theme.colors.text }]}>{i18n.t('common.skills')}</Text>
                    <View style={styles.tags}>
                      {parsed.data.skills.map((skill) => (
                        <Tag key={skill}>{skill}</Tag>
                      ))}
                    </View>
                  </View>
                  {parsed.data.years_experience ? (
                    <View style={styles.parsedRow}>
                      <Text style={[styles.parsedLabel, { color: theme.colors.text }]}>{i18n.t('common.experience')}</Text>
                      <Text style={[styles.parsedValue, { color: theme.colors.textSecondary }]}>
                        {parsed.data.years_experience}+ {i18n.t('common.years')}
                      </Text>
                    </View>
                  ) : null}
                  {parsed.data.education_level ? (
                    <View style={styles.parsedRow}>
                      <Text style={[styles.parsedLabel, { color: theme.colors.text }]}>{i18n.t('common.education')}</Text>
                      <Text style={[styles.parsedValue, { color: theme.colors.textSecondary }]}>
                        {parsed.data.education_level}
                      </Text>
                    </View>
                  ) : null}
                </View>
              ) : (
                <View style={styles.notParsed}>
                  <Text style={[styles.metaMuted, { color: theme.colors.textMuted }]}>
                    {i18n.t('jobDetail.notParsed')}
                  </Text>
                  <Button variant="ghost" size="sm" onPress={parseNow} loading={parseJob.isPending}>
                    {i18n.t('jobDetail.parseNow')}
                  </Button>
                </View>
              )}
            </View>

            <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
              <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>
                {i18n.t('common.description')}
              </Text>
              {descriptionHtml ? (
                <RenderHTML
                  source={{ html: descriptionHtml }}
                  contentWidth={Math.max(width - 64, 240)}
                  baseStyle={{ color: theme.colors.text, fontSize: 15, lineHeight: 22 }}
                />
              ) : (
                <Text style={[styles.metaMuted, { color: theme.colors.textMuted }]}>
                  {i18n.t('jobDetail.noDescription')}
                </Text>
              )}
            </View>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  content: {
    padding: 16,
    gap: 12,
  },
  panel: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
    gap: 10,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    flexShrink: 1,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  meta: {
    fontSize: 14,
  },
  metaMuted: {
    fontSize: 13,
  },
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
  },
  link: {
    fontSize: 14,
    fontWeight: '600',
  },
  actions: {
    gap: 8,
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 4,
  },
  parsed: {
    gap: 10,
  },
  parsedRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  parsedLabel: {
    fontWeight: '600',
    fontSize: 14,
    minWidth: 96,
  },
  parsedValue: {
    fontSize: 14,
    flex: 1,
  },
  notParsed: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
});
