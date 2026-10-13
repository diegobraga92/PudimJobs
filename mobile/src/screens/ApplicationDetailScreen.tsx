import { RouteProp, useNavigation, useRoute } from '@react-navigation/native';
import { useState } from 'react';
import {
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { RenderHTML } from 'react-native-render-html';

import { CvPanel } from '@/components/cv/CvPanel';
import { AppHeader } from '@/components/layout/AppHeader';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Icon } from '@/components/icons/Icon';
import { Input } from '@/components/ui/Input';
import { Panel } from '@/components/ui/Panel';
import { Select } from '@/components/ui/Select';
import { Skeleton } from '@/components/ui/Skeleton';
import { TextArea } from '@/components/ui/TextArea';
import { useConfirm } from '@/components/confirm/ConfirmProvider';
import { useToast } from '@/components/toast/ToastProvider';
import {
  useApplication,
  useDeleteApplication,
  useUpdateApplication,
} from '@/hooks/useApplications';
import { useI18n } from '@/i18n/I18nProvider';
import { ApplicationsStackParamList } from '@/navigation/types';
import { useTheme } from '@/theme/ThemeProvider';
import { ApplicationDetail, ApplicationInput, ApplicationStatus } from '@/types';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];

/**
 * Per-application workspace (mobile).
 *
 * One place for a single application: the job it targets, the pipeline fields
 * that used to live in the kanban modal (status, applied date, notes,
 * retrospective) and — new — the CV panel holding the tailored CV and its ATS
 * check. Mirrors the web `/applications/:id` page.
 */
export function ApplicationDetailScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const navigation = useNavigation();
  const route = useRoute<RouteProp<ApplicationsStackParamList, 'ApplicationDetail'>>();
  const { width } = useWindowDimensions();
  const { id } = route.params;

  const { data: application, isPending, error } = useApplication(id);
  const update = useUpdateApplication(id);
  const removeApp = useDeleteApplication();

  const [actionError, setActionError] = useState<string | null>(null);

  const displayError = (error ? i18n.t('errors.failedLoadApplication') : null) ?? actionError;

  const save = (payload: Partial<ApplicationInput>) => {
    if (!application) {
      return;
    }
    setActionError(null);
    update.mutate(payload, {
      onSuccess: () => toast.success(i18n.t('applications.detailsSaved')),
      onError: () => toast.error(i18n.t('errors.failedUpdateApplication')),
    });
  };

  const changeStatus = (status: ApplicationStatus) => {
    if (!application || application.status === status) {
      return;
    }
    update.mutate(
      { status },
      {
        onSuccess: () =>
          toast.success(i18n.t('applications.movedTo', { status: i18n.t(`pipeline.${status}`) })),
        onError: () => toast.error(i18n.t('errors.failedUpdateStatus')),
      },
    );
  };

  const remove = async () => {
    if (!application) {
      return;
    }
    const confirmed = await confirm.confirm({
      title: i18n.t('applications.removeTitle'),
      message: i18n.t('applications.removeMessage', { title: application.job_title }),
      confirmLabel: i18n.t('common.remove'),
      cancelLabel: i18n.t('applications.keepIt'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    removeApp.mutate(application.id, {
      onSuccess: () => {
        toast.success(i18n.t('applications.removed'));
        navigation.goBack();
      },
      onError: () => toast.error(i18n.t('errors.failedDeleteApplication')),
    });
  };

  const description = application?.job_description?.trim() || null;
  const renderWidth = Math.max(200, width - 72);

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <AppHeader
        title={application?.job_title ?? i18n.t('applications.workspace')}
        back
        onLeftPress={() => navigation.goBack()}
      />
      <ScrollView contentContainerStyle={styles.content} style={styles.flex}>
        {displayError ? <Alert tone="error">{displayError}</Alert> : null}

        {isPending ? <Skeleton width="70%" height={20} /> : null}

        {application ? (
          <>
            <ApplicationForm
              key={application.updated_at}
              application={application}
              saving={update.isPending}
              onChangeStatus={changeStatus}
              onSave={save}
              onDelete={() => void remove()}
            />

            <Panel style={styles.panel}>
              <Text style={[styles.sectionTitle, { color: theme.colors.primary }]}>
                {i18n.t('applications.jobDescription')}
              </Text>
              {description ? (
                <RenderHTML
                  contentWidth={renderWidth}
                  source={{ html: description }}
                  baseStyle={{ color: theme.colors.textSecondary, fontSize: 14 }}
                />
              ) : (
                <Text style={[styles.muted, { color: theme.colors.textMuted }]}>
                  {i18n.t('applications.noDescription')}
                </Text>
              )}
            </Panel>

            <CvPanel
              jobId={application.job_id}
              applicationId={application.id}
              linkedCvId={application.generated_cv_id}
            />
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

/**
 * Pipeline fields + notes editor for one application.
 *
 * Mounted with `key={application.updated_at}` so a refetch re-seeds the drafts
 * from the server without a `setState`-in-effect.
 */
function ApplicationForm({
  application,
  saving,
  onChangeStatus,
  onSave,
  onDelete,
}: {
  application: ApplicationDetail;
  saving: boolean;
  onChangeStatus: (status: ApplicationStatus) => void;
  onSave: (payload: Partial<ApplicationInput>) => void;
  onDelete: () => void;
}) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const [notes, setNotes] = useState(application.notes ?? '');
  const [lessons, setLessons] = useState(application.lessons_learned ?? '');
  const [appliedDate, setAppliedDate] = useState(application.applied_date ?? '');

  const submit = () =>
    onSave({
      notes: notes.trim() || null,
      lessons_learned: lessons.trim() || null,
      applied_date: appliedDate.trim() || null,
    });

  return (
    <Panel style={styles.panel}>
      <Text style={[styles.company, { color: theme.colors.textMuted }]}>
        {application.job_company}
      </Text>
      {application.job_url ? (
        <Pressable
          onPress={() => void Linking.openURL(application.job_url as string)}
          accessibilityRole="link"
          style={styles.linkRow}
        >
          <Text style={[styles.link, { color: theme.colors.accent }]}>
            {i18n.t('applications.viewPosting')}
          </Text>
          <Icon name="external-link" size={13} color={theme.colors.accent} />
        </Pressable>
      ) : null}

      <FormField label={i18n.t('applications.moveToStatus')}>
        <Select<ApplicationStatus>
          value={application.status}
          options={STATUSES.map((status) => ({
            label: i18n.t(`pipeline.${status}`),
            value: status,
          }))}
          onValueChange={onChangeStatus}
        />
      </FormField>

      <FormField label={i18n.t('applications.appliedOn')}>
        <Input
          value={appliedDate}
          onChangeText={setAppliedDate}
          placeholder="YYYY-MM-DD"
          autoCapitalize="none"
          autoCorrect={false}
        />
      </FormField>

      <FormField label={i18n.t('applications.notes')}>
        <TextArea value={notes} onChangeText={setNotes} minHeight={90} />
      </FormField>

      <FormField label={i18n.t('applications.lessonsLearned')}>
        <TextArea
          value={lessons}
          onChangeText={setLessons}
          minHeight={90}
          placeholder={i18n.t('applications.lessonsPlaceholder')}
        />
      </FormField>

      <View style={styles.actions}>
        <Button onPress={submit} loading={saving}>
          {i18n.t('applications.saveDetails')}
        </Button>
        <Button variant="danger" onPress={onDelete}>
          {i18n.t('common.delete')}
        </Button>
      </View>
    </Panel>
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
    paddingBottom: 32,
    gap: 12,
  },
  panel: {
    gap: 10,
  },
  company: {
    fontSize: 14,
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
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  muted: {
    fontSize: 13,
  },
});
