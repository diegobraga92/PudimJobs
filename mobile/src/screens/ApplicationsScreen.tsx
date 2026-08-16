import { useMemo, useState } from 'react';
import { Linking, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Icon } from '@/components/icons/Icon';
import { Select } from '@/components/ui/Select';
import { Skeleton } from '@/components/ui/Skeleton';
import { useConfirm } from '@/components/confirm/ConfirmProvider';
import { useToast } from '@/components/toast/ToastProvider';
import {
  useApplications,
  useDeleteApplication,
  useUpdateApplication,
} from '@/hooks/useApplications';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { ThemeColors } from '@/theme/tokens';
import { Application, ApplicationStatus } from '@/types';
import { dateLocale, mediumDate } from '@/utils/dates';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];

/** Status-dot color derived from theme tokens (adapts to dark mode, like the web). */
function statusDotColor(status: ApplicationStatus, colors: ThemeColors): string {
  switch (status) {
    case 'saved':
      return colors.info;
    case 'applied':
    case 'interview':
      return colors.warning;
    case 'offer':
      return colors.success;
    case 'rejected':
      return colors.danger;
  }
}

/** Application pipeline — mirrors the web kanban (5 status columns + detail modal). */
export function ApplicationsScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const { data: applications = [], isPending, error } = useApplications();
  const [selected, setSelected] = useState<Application | null>(null);

  const columns = useMemo(() => {
    const cols: Record<ApplicationStatus, Application[]> = {
      saved: [],
      applied: [],
      interview: [],
      offer: [],
      rejected: [],
    };
    for (const app of applications) {
      cols[app.status].push(app);
    }
    return cols;
  }, [applications]);

  return (
    <ScrollView style={[styles.container, { backgroundColor: theme.colors.bg }]} contentContainerStyle={styles.content}>
      <Text style={[styles.title, { color: theme.colors.text }]}>{i18n.t('applications.title')}</Text>
      <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
        {i18n.t('applications.total', { total: applications.length })}
      </Text>

      {error ? <Alert tone="error">{i18n.t('errors.failedLoadApplications')}</Alert> : null}

      {isPending && applications.length === 0 ? (
        <View style={styles.skeletons}>
          {[1, 2, 3].map((item) => (
            <View key={item} style={[styles.skeletonCard, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
              <Skeleton width="50%" height={16} />
              <Skeleton width="70%" height={13} style={{ marginTop: 10 }} />
            </View>
          ))}
        </View>
      ) : null}

      {!isPending && applications.length === 0 ? (
        <EmptyState
          icon="kanban"
          title={i18n.t('applications.emptyTitle')}
          hint={i18n.t('applications.emptyHint')}
        />
      ) : null}

      {applications.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.board}>
          {STATUSES.map((status) => (
            <View
              key={status}
              style={[styles.column, { backgroundColor: theme.colors.kanbanColumn, borderColor: theme.colors.border }]}
            >
              <View style={styles.columnHead}>
                <View style={[styles.statusDot, { backgroundColor: statusDotColor(status, theme.colors) }]} />
                <Text style={[styles.columnTitle, { color: theme.colors.text }]}>
                  {i18n.t(`pipeline.${status}`)}
                </Text>
                <Text style={[styles.columnCount, { color: theme.colors.textMuted }]}>
                  {columns[status].length}
                </Text>
              </View>
              <ScrollView nestedScrollEnabled style={styles.columnScroll} contentContainerStyle={styles.columnBody}>
                {columns[status].length === 0 ? (
                  <Text style={[styles.dropHint, { color: theme.colors.textFaint }]}>
                    {i18n.t('applications.dropHere')}
                  </Text>
                ) : (
                  columns[status].map((app) => (
                    <Pressable
                      key={app.id}
                      onPress={() => setSelected(app)}
                      accessibilityRole="button"
                      style={({ pressed }) => [
                        styles.card,
                        { backgroundColor: theme.colors.surface, borderColor: theme.colors.border, opacity: pressed ? 0.9 : 1 },
                      ]}
                    >
                      <Text style={[styles.cardTitle, { color: theme.colors.text }]} numberOfLines={2}>
                        {app.job_title}
                      </Text>
                      <Text style={[styles.cardCompany, { color: theme.colors.textSecondary }]} numberOfLines={1}>
                        {app.job_company}
                      </Text>
                      {app.applied_date ? (
                        <View style={styles.cardDateRow}>
                          <Icon name="calendar" size={12} color={theme.colors.textFaint} />
                          <Text style={[styles.cardDate, { color: theme.colors.textMuted }]}>
                            {i18n.t('pipeline.applied')} {mediumDate(app.applied_date, dateLocale(i18n.lang))}
                          </Text>
                        </View>
                      ) : null}
                    </Pressable>
                  ))
                )}
              </ScrollView>
            </View>
          ))}
        </ScrollView>
      ) : null}

      {selected ? (
        <ApplicationModal application={selected} onClose={() => setSelected(null)} />
      ) : null}
    </ScrollView>
  );
}


function ApplicationModal({ application, onClose }: { application: Application; onClose: () => void }) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const updateApp = useUpdateApplication(application.id);
  const deleteApp = useDeleteApplication();

  const changeStatus = (status: ApplicationStatus) => {
    updateApp.mutate(
      { status },
      {
        onSuccess: () => {
          toast.success(i18n.t('applications.movedTo', { status: i18n.t(`pipeline.${status}`) }));
          onClose();
        },
        onError: () => toast.error(i18n.t('errors.failedUpdateStatus')),
      },
    );
  };

  const remove = async () => {
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
    deleteApp.mutate(application.id, {
      onSuccess: () => {
        toast.success(i18n.t('applications.removed'));
        onClose();
      },
      onError: () => toast.error(i18n.t('errors.failedDeleteApplication')),
    });
  };

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable
          onPress={() => undefined}
          style={[styles.modalCard, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}
        >
          <Text style={[styles.modalTitle, { color: theme.colors.text }]}>{application.job_title}</Text>
          <Text style={[styles.modalCompany, { color: theme.colors.textMuted }]}>{application.job_company}</Text>

          {application.job_url ? (
            <Pressable
              onPress={() => void Linking.openURL(application.job_url as string)}
              accessibilityRole="link"
              style={styles.linkRow}
            >
              <Text style={[styles.link, { color: theme.colors.accent }]}>{i18n.t('applications.viewPosting')}</Text>
              <Icon name="external-link" size={13} color={theme.colors.accent} />
            </Pressable>
          ) : null}

          {application.notes ? (
            <Text style={[styles.notes, { color: theme.colors.textSecondary }]}>{application.notes}</Text>
          ) : null}

          <Text style={[styles.modalLabel, { color: theme.colors.text }]}>
            {i18n.t('applications.moveToStatus')}
          </Text>
          <Select<ApplicationStatus>
            value={application.status}
            options={STATUSES.map((status) => ({ label: i18n.t(`pipeline.${status}`), value: status }))}
            onValueChange={changeStatus}
          />

          <View style={styles.modalActions}>
            <Button variant="danger" onPress={() => void remove()}>
              {i18n.t('common.delete')}
            </Button>
            <Button variant="ghost" onPress={onClose}>
              {i18n.t('common.close')}
            </Button>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}



const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
  },
  subtitle: {
    fontSize: 13,
    marginTop: 2,
    marginBottom: 8,
  },
  skeletons: {
    gap: 12,
    marginTop: 12,
  },
  skeletonCard: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
  },
  board: {
    gap: 12,
    paddingVertical: 12,
    alignItems: 'flex-start',
  },
  column: {
    width: 260,
    borderRadius: 12,
    borderWidth: 1,
    padding: 10,
    maxHeight: 520,
  },
  columnHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
    paddingHorizontal: 2,
  },
  statusDot: {
    width: 9,
    height: 9,
    borderRadius: 9999,
  },
  columnTitle: {
    fontSize: 14,
    fontWeight: '700',
    flex: 1,
  },
  columnCount: {
    fontSize: 13,
  },
  columnBody: {
    gap: 8,
  },
  columnScroll: {
    flexShrink: 1,
  },
  dropHint: {
    fontSize: 13,
    textAlign: 'center',
    paddingVertical: 16,
    fontStyle: 'italic',
  },
  card: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    gap: 6,
  },
  cardTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  cardCompany: {
    fontSize: 13,
  },
  cardDateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  cardDate: {
    fontSize: 12,
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.5)',
    justifyContent: 'center',
    padding: 24,
  },
  modalCard: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 20,
    maxWidth: 420,
    width: '100%',
    alignSelf: 'center',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  modalCompany: {
    fontSize: 14,
    marginTop: 2,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
    marginTop: 10,
  },
  link: {
    fontSize: 14,
    fontWeight: '600',
  },
  notes: {
    fontSize: 14,
    marginTop: 10,
    lineHeight: 20,
  },
  modalLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginTop: 14,
    marginBottom: 6,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 16,
  },
});
