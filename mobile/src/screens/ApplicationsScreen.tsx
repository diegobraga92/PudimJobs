import { DrawerActions, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { AppHeader } from '@/components/layout/AppHeader';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { Icon } from '@/components/icons/Icon';
import { Skeleton } from '@/components/ui/Skeleton';
import { Switch } from '@/components/ui/Switch';
import { useApplications } from '@/hooks/useApplications';
import { useI18n } from '@/i18n/I18nProvider';
import { ApplicationsStackParamList } from '@/navigation/types';
import { useTheme } from '@/theme/ThemeProvider';
import { ThemeColors } from '@/theme/tokens';
import { Application, ApplicationStatus } from '@/types';
import { dateLocale, mediumDate } from '@/utils/dates';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];
/** Columns shown until the user asks for the rejected one (mirrors the web board). */
const VISIBLE_STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer'];

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

/** Application pipeline — mirrors the web kanban; cards open the workspace. */
export function ApplicationsScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const navigation = useNavigation<NativeStackNavigationProp<ApplicationsStackParamList>>();
  const { data: applications = [], isPending, error } = useApplications();
  /** Rejected applications are history, not work in progress: hidden by default. */
  const [showRejected, setShowRejected] = useState(false);
  const statuses = showRejected ? STATUSES : VISIBLE_STATUSES;

  const openWorkspace = (application: Application) =>
    navigation.navigate('ApplicationDetail', { id: application.id });

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
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <AppHeader
        title={i18n.t('layout.nav.applications')}
        onLeftPress={() => navigation.dispatch(DrawerActions.openDrawer())}
      />
      <ScrollView contentContainerStyle={styles.content} style={styles.flex}>
        <Text style={[styles.title, { color: theme.colors.text }]}>
          {i18n.t('applications.title')}
        </Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
          {i18n.t('applications.total', { total: applications.length })}
        </Text>

        <View style={styles.toggleRow}>
          <Text style={[styles.toggleLabel, { color: theme.colors.text }]}>
            {i18n.t('applications.showRejected')}
          </Text>
          <Switch
            value={showRejected}
            onValueChange={setShowRejected}
            accessibilityLabel={i18n.t('applications.showRejected')}
          />
        </View>

        {error ? <Alert tone="error">{i18n.t('errors.failedLoadApplications')}</Alert> : null}

        {isPending && applications.length === 0 ? (
          <View style={styles.skeletons}>
            {[1, 2, 3].map((item) => (
              <View
                key={item}
                style={[
                  styles.skeletonCard,
                  { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
                ]}
              >
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
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.board}
          >
            {statuses.map((status) => (
              <View
                key={status}
                style={[
                  styles.column,
                  { backgroundColor: theme.colors.kanbanColumn, borderColor: theme.colors.border },
                ]}
              >
                <View style={styles.columnHead}>
                  <View
                    style={[
                      styles.statusDot,
                      { backgroundColor: statusDotColor(status, theme.colors) },
                    ]}
                  />
                  <Text style={[styles.columnTitle, { color: theme.colors.text }]}>
                    {i18n.t(`pipeline.${status}`)}
                  </Text>
                  <Text style={[styles.columnCount, { color: theme.colors.textMuted }]}>
                    {columns[status].length}
                  </Text>
                </View>
                <ScrollView
                  nestedScrollEnabled
                  style={styles.columnScroll}
                  contentContainerStyle={styles.columnBody}
                >
                  {columns[status].length === 0 ? (
                    <Text style={[styles.dropHint, { color: theme.colors.textFaint }]}>
                      {i18n.t('applications.dropHere')}
                    </Text>
                  ) : (
                    columns[status].map((app) => (
                      <Pressable
                        key={app.id}
                        onPress={() => openWorkspace(app)}
                        accessibilityRole="button"
                        style={({ pressed }) => [
                          styles.card,
                          {
                            backgroundColor: theme.colors.surface,
                            borderColor: theme.colors.border,
                            opacity: pressed ? 0.9 : 1,
                          },
                        ]}
                      >
                        <Text
                          style={[styles.cardTitle, { color: theme.colors.text }]}
                          numberOfLines={2}
                        >
                          {app.job_title}
                        </Text>
                        <Text
                          style={[styles.cardCompany, { color: theme.colors.textSecondary }]}
                          numberOfLines={1}
                        >
                          {app.job_company}
                        </Text>
                        {app.applied_date ? (
                          <View style={styles.cardDateRow}>
                            <Icon name="calendar" size={12} color={theme.colors.textFaint} />
                            <Text style={[styles.cardDate, { color: theme.colors.textMuted }]}>
                              {i18n.t('pipeline.applied')}{' '}
                              {mediumDate(app.applied_date, dateLocale(i18n.lang))}
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
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    paddingVertical: 4,
  },
  toggleLabel: {
    fontSize: 14,
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
});
