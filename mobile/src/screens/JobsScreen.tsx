import AsyncStorage from '@react-native-async-storage/async-storage';
import { DrawerActions, useNavigation } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useEffect, useMemo, useRef, useState } from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';

import { hideJob as hideJobApi, unhideJob as unhideJobApi } from '@/api/jobs';
import { AppHeader } from '@/components/layout/AppHeader';
import { AddJobForm, AddJobFields } from '@/components/jobs/AddJobForm';
import { JobCard } from '@/components/jobs/JobCard';
import { SearchForm, SearchFields } from '@/components/jobs/SearchForm';
import { Onboarding } from '@/components/onboarding/Onboarding';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Icon } from '@/components/icons/Icon';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/toast/ToastProvider';
import { useCreateJob, useJobs } from '@/hooks/useJobs';
import { usePipelineMap } from '@/hooks/useApplications';
import { useI18n } from '@/i18n/I18nProvider';
import { JobsStackParamList } from '@/navigation/types';
import { useTheme } from '@/theme/ThemeProvider';
import { JobCreateInput, JobFilters, JobSummary } from '@/types';
import { parseList } from '@/utils/lists';

const ONBOARDING_KEY = 'pudimjobs_onboarding_dismissed';
const PAGE_SIZE = 12;

const EMPTY_SEARCH: SearchFields = { q: '', company: '', tags: '', date_from: '', date_to: '' };
const EMPTY_FORM: AddJobFields = {
  title: '',
  company: '',
  url: '',
  posted_date: '',
  tags: '',
  description: '',
};

export function JobsScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const navigation = useNavigation<NativeStackNavigationProp<JobsStackParamList>>();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [searchFields, setSearchFields] = useState<SearchFields>(EMPTY_SEARCH);
  const [filters, setFilters] = useState<JobFilters>({});
  const [hideApplied, setHideApplied] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [formFields, setFormFields] = useState<AddJobFields>(EMPTY_FORM);
  const [onboardingDismissed, setOnboardingDismissed] = useState(true);

  const listRef = useRef<FlatList<JobSummary>>(null);

  const { data: jobs = [], isPending, error } = useJobs(filters);
  const pipelineMap = usePipelineMap();
  const createJob = useCreateJob();

  useEffect(() => {
    void AsyncStorage.getItem(ONBOARDING_KEY).then((value) => {
      setOnboardingDismissed(value === '1');
    });
  }, []);

  const dismissOnboarding = () => {
    setOnboardingDismissed(true);
    void AsyncStorage.setItem(ONBOARDING_KEY, '1');
  };

  const search = () => {
    const validDate = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value);
    if (
      (searchFields.date_from && !validDate(searchFields.date_from)) ||
      (searchFields.date_to && !validDate(searchFields.date_to))
    ) {
      toast.error(i18n.t('errors.invalidDate'));
      return;
    }
    setFilters({
      q: searchFields.q || undefined,
      company: searchFields.company || undefined,
      tags: searchFields.tags || undefined,
      date_from: searchFields.date_from || undefined,
      date_to: searchFields.date_to || undefined,
      hide_applied: hideApplied || undefined,
      include_hidden: showHidden || undefined,
    });
    setPage(1);
  };

  const toggleHideApplied = () => {
    const next = !hideApplied;
    setHideApplied(next);
    setFilters((filters) => ({ ...filters, hide_applied: next || undefined }));
    setPage(1);
  };

  const toggleShowHidden = () => {
    const next = !showHidden;
    setShowHidden(next);
    setFilters((filters) => ({ ...filters, include_hidden: next || undefined }));
    setPage(1);
  };

  const pagedJobs = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return jobs.slice(start, start + PAGE_SIZE);
  }, [jobs, page]);

  const pageCount = Math.max(1, Math.ceil(jobs.length / PAGE_SIZE));

  const rangeLabel = useMemo(() => {
    if (jobs.length === 0) {
      return i18n.t('jobs.zeroResults');
    }
    const start = (page - 1) * PAGE_SIZE + 1;
    const end = Math.min(page * PAGE_SIZE, jobs.length);
    return i18n.t('jobs.rangeLabel', { start, end, total: jobs.length });
  }, [jobs.length, page, i18n]);

  const goToPage = (next: number) => {
    if (next < 1 || next > pageCount) {
      return;
    }
    setPage(next);
    listRef.current?.scrollToOffset({ offset: 0, animated: true });
  };

  const hideToggle = (job: JobSummary) => {
    const request = job.hidden ? unhideJobApi(job.id) : hideJobApi(job.id);
    request
      .then(() => {
        toast.success(job.hidden ? i18n.t('jobs.jobUnhidden') : i18n.t('jobs.jobHidden'));
        void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      })
      .catch(() => toast.error(i18n.t('errors.failedHideJob')));
  };

  const saveJob = () => {
    if (!formFields.title.trim() || !formFields.company.trim()) {
      return;
    }
    const payload: JobCreateInput = {
      title: formFields.title,
      company: formFields.company,
      url: formFields.url || null,
      posted_date: formFields.posted_date || null,
      description: formFields.description || null,
      tags: parseList(formFields.tags),
    };
    createJob.mutate(payload, {
      onSuccess: () => {
        setShowForm(false);
        setFormFields(EMPTY_FORM);
        toast.success(i18n.t('jobs.jobAdded'));
        void queryClient.invalidateQueries({ queryKey: ['applications'] });
      },
      onError: () => toast.error(i18n.t('errors.failedCreateJob')),
    });
  };

  const header = (
    <View style={styles.content}>
      {error ? <Alert tone="error">{i18n.t('errors.failedLoadJobs')}</Alert> : null}

      {showForm ? (
        <AddJobForm
          fields={formFields}
          onChange={setFormFields}
          onCancel={() => setShowForm(false)}
          onSave={saveJob}
          saving={createJob.isPending}
        />
      ) : null}

      <SearchForm
        fields={searchFields}
        onChange={setSearchFields}
        hideApplied={hideApplied}
        showHidden={showHidden}
        onToggleHideApplied={toggleHideApplied}
        onToggleShowHidden={toggleShowHidden}
        onSearch={search}
        searching={isPending}
      />

      {!onboardingDismissed && !isPending && jobs.length === 0 ? (
        <Onboarding onDismiss={dismissOnboarding} />
      ) : null}

      {isPending && jobs.length === 0 ? (
        <View style={styles.skeletonGrid}>
          {[1, 2, 3, 4].map((item) => (
            <View
              key={item}
              style={[
                styles.skeletonCard,
                { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
              ]}
            >
              <Skeleton width="70%" height={18} />
              <Skeleton width="45%" height={14} style={{ marginTop: 10 }} />
              <Skeleton width="90%" height={13} style={{ marginTop: 14 }} />
            </View>
          ))}
        </View>
      ) : null}

      {!isPending && jobs.length === 0 ? (
        <EmptyState
          icon="briefcase"
          title={i18n.t('jobs.noJobsFound')}
          hint={i18n.t('jobs.noJobsHint')}
          action={
            <Button
              onPress={() => {
                setFormFields(EMPTY_FORM);
                setShowForm(true);
              }}
            >
              {i18n.t('jobs.addFirstJob')}
            </Button>
          }
        />
      ) : null}
    </View>
  );

  const footer =
    !isPending && jobs.length > 0 && pageCount > 1 ? (
      <View style={[styles.pagination, { borderTopColor: theme.colors.border }]}>
        <Button variant="ghost" size="sm" disabled={page <= 1} onPress={() => goToPage(page - 1)}>
          {i18n.t('common.previous')}
        </Button>
        <Text style={[styles.range, { color: theme.colors.textMuted }]}>{rangeLabel}</Text>
        <Button
          variant="ghost"
          size="sm"
          disabled={page >= pageCount}
          onPress={() => goToPage(page + 1)}
        >
          {i18n.t('common.next')}
        </Button>
      </View>
    ) : null;

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <AppHeader
        title={i18n.t('jobs.title')}
        onLeftPress={() => navigation.dispatch(DrawerActions.openDrawer())}
        right={
          <Button
            size="sm"
            icon={<Icon name="plus" size={16} color={theme.colors.onPrimary} />}
            onPress={() => {
              setFormFields(EMPTY_FORM);
              setShowForm((current) => !current);
            }}
          >
            {i18n.t('jobs.addJob')}
          </Button>
        }
      />
      <FlatList
        ref={listRef}
        data={pagedJobs}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        ListHeaderComponent={header}
        ListFooterComponent={footer}
        renderItem={({ item }) => (
          <JobCard
            job={item}
            pipelineStatus={pipelineMap[item.id]}
            onOpen={() => navigation.navigate('JobDetail', { id: item.id })}
            onToggleHidden={() => hideToggle(item)}
          />
        )}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        keyboardShouldPersistTaps="handled"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingHorizontal: 16,
  },
  listContent: {
    paddingBottom: 32,
  },
  skeletonGrid: {
    gap: 12,
  },
  skeletonCard: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
  },
  pagination: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 12,
    marginTop: 12,
    borderTopWidth: 1,
  },
  range: {
    fontSize: 13,
  },
  separator: {
    height: 12,
  },
});
