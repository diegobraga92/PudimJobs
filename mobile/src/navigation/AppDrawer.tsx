import { createDrawerNavigator } from '@react-navigation/drawer';
import { DrawerActions, useNavigation } from '@react-navigation/native';

import { AppHeader } from '@/components/layout/AppHeader';
import { DrawerContent } from '@/components/layout/DrawerContent';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { AdminScreen } from '@/screens/AdminScreen';
import { AlertsScreen } from '@/screens/AlertsScreen';
import { ApplicationsScreen } from '@/screens/ApplicationsScreen';
import { CvEditorScreen } from '@/screens/CvEditorScreen';
import { NotificationsScreen } from '@/screens/NotificationsScreen';
import { SourcesScreen } from '@/screens/SourcesScreen';
import { JobsStack } from './JobsStack';
import { AppDrawerParamList } from './types';

const Drawer = createDrawerNavigator<AppDrawerParamList>();

/** Screen wrapper: renders the app bar with the drawer toggle above the content. */
function WithAppBar({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const navigation = useNavigation();
  return (
    <>
      <AppHeader title={title} onMenuPress={() => navigation.dispatch(DrawerActions.openDrawer())} />
      {children}
    </>
  );
}

function WrappedSourcesScreen() {
  const i18n = useI18n();
  return (
    <WithAppBar title={i18n.t('layout.nav.sources')}>
      <SourcesScreen />
    </WithAppBar>
  );
}

function WrappedCvScreen() {
  const i18n = useI18n();
  return (
    <WithAppBar title={i18n.t('layout.nav.masterCv')}>
      <CvEditorScreen />
    </WithAppBar>
  );
}

function WrappedApplicationsScreen() {
  const i18n = useI18n();
  return (
    <WithAppBar title={i18n.t('layout.nav.applications')}>
      <ApplicationsScreen />
    </WithAppBar>
  );
}

function WrappedAlertsScreen() {
  const i18n = useI18n();
  return (
    <WithAppBar title={i18n.t('layout.nav.alerts')}>
      <AlertsScreen />
    </WithAppBar>
  );
}

function WrappedNotificationsScreen() {
  const i18n = useI18n();
  return (
    <WithAppBar title={i18n.t('layout.nav.notifications')}>
      <NotificationsScreen />
    </WithAppBar>
  );
}

function WrappedAdminScreen() {
  const i18n = useI18n();
  return (
    <WithAppBar title={i18n.t('layout.nav.admin')}>
      <AdminScreen />
    </WithAppBar>
  );
}

/** Main app shell — drawer mirrors the web sidebar; each item maps to a screen. */
export function AppDrawer() {
  const { theme } = useTheme();
  const i18n = useI18n();
  return (
    <Drawer.Navigator
      drawerContent={(props) => <DrawerContent {...props} />}
      screenOptions={{
        headerShown: false,
        drawerType: 'front',
        swipeEdgeWidth: 60,
        sceneStyle: { backgroundColor: theme.colors.bg },
      }}
    >
      <Drawer.Screen name="Jobs" component={JobsStack} options={{ title: i18n.t('layout.nav.jobs') }} />
      <Drawer.Screen name="Sources" component={WrappedSourcesScreen} options={{ title: i18n.t('layout.nav.sources') }} />
      <Drawer.Screen name="MasterCv" component={WrappedCvScreen} options={{ title: i18n.t('layout.nav.masterCv') }} />
      <Drawer.Screen name="Applications" component={WrappedApplicationsScreen} options={{ title: i18n.t('layout.nav.applications') }} />
      <Drawer.Screen name="Alerts" component={WrappedAlertsScreen} options={{ title: i18n.t('layout.nav.alerts') }} />
      <Drawer.Screen name="Notifications" component={WrappedNotificationsScreen} options={{ title: i18n.t('layout.nav.notifications') }} />
      <Drawer.Screen name="Admin" component={WrappedAdminScreen} options={{ title: i18n.t('layout.nav.admin') }} />
    </Drawer.Navigator>
  );
}
