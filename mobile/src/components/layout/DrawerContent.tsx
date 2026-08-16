import { DrawerContentComponentProps } from '@react-navigation/drawer';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Icon, IconName } from '@/components/icons/Icon';
import { useHealth } from '@/hooks/useHealth';
import { useNotifications } from '@/hooks/useNotifications';
import { useI18n } from '@/i18n/I18nProvider';
import { useAuthStore } from '@/store/auth';
import { useTheme } from '@/theme/ThemeProvider';

interface NavItem {
  labelKey: string;
  /** Drawer screen name from AppDrawerParamList. */
  route: keyof import('@/navigation/types').AppDrawerParamList;
  icon: IconName;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { labelKey: 'layout.nav.jobs', route: 'Jobs', icon: 'briefcase' },
  { labelKey: 'layout.nav.sources', route: 'Sources', icon: 'globe' },
  { labelKey: 'layout.nav.masterCv', route: 'MasterCv', icon: 'file-text' },
  { labelKey: 'layout.nav.applications', route: 'Applications', icon: 'kanban' },
  { labelKey: 'layout.nav.alerts', route: 'Alerts', icon: 'bell' },
  { labelKey: 'layout.nav.notifications', route: 'Notifications', icon: 'bell-ring' },
  { labelKey: 'layout.nav.admin', route: 'Admin', icon: 'shield-check', adminOnly: true },
];

/** Drawer content — mirrors the web sidebar (brand, nav, user chip, status, toggles). */
export function DrawerContent(props: DrawerContentComponentProps) {
  const { state, navigation } = props;
  const { theme, toggle, isDark } = useTheme();
  const i18n = useI18n();
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);

  const { data: health } = useHealth(30_000);
  const { data: notifications } = useNotifications();
  const unread = notifications?.unread ?? 0;

  const online = health?.status === 'ok';
  const activeIndex = state.index;

  const navigate = (route: NavItem['route']) => {
    navigation.navigate(route as never);
  };

  const signOut = () => {
    clear();
  };

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.sidebarBg }]}>
      <View style={styles.brandRow}>
        <View style={styles.brandMark}>
          <Icon name="briefcase" size={22} color={theme.colors.onPrimary} />
        </View>
        <Text style={styles.brandName}>PudimJobs</Text>
      </View>

      <ScrollView style={styles.nav} contentContainerStyle={styles.navContent}>
        {NAV_ITEMS.map((item, index) => {
          if (item.adminOnly && user?.role !== 'admin') {
            return null;
          }
          const active = activeIndex === index;
          return (
            <Pressable
              key={item.route}
              onPress={() => navigate(item.route)}
              accessibilityRole="button"
              style={[
                styles.navItem,
                active
                  ? { backgroundColor: theme.colors.sidebarActive }
                  : { backgroundColor: 'transparent' },
              ]}
            >
              <Icon
                name={item.icon}
                size={19}
                color={active ? theme.colors.onPrimary : theme.colors.sidebarText}
              />
              <Text
                style={[
                  styles.navLabel,
                  { color: active ? theme.colors.onPrimary : theme.colors.sidebarText },
                ]}
              >
                {i18n.t(item.labelKey)}
              </Text>
              {item.route === 'Notifications' && unread > 0 ? (
                <View style={styles.navBadge}>
                  <Text style={styles.navBadgeText}>{unread > 99 ? '99+' : unread}</Text>
                </View>
              ) : null}
            </Pressable>
          );
        })}
      </ScrollView>

      <View style={styles.footer}>
        {user ? (
          <View style={styles.userChip}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{user.email.charAt(0).toUpperCase()}</Text>
            </View>
            <Text style={styles.userEmail} numberOfLines={1}>
              {user.email}
            </Text>
          </View>
        ) : null}

        <View style={styles.statusRow}>
          <View style={[styles.statusDot, online ? styles.statusDotOnline : null]} />
          <Text style={styles.apiStatus}>
            {online ? i18n.t('layout.apiOnline') : i18n.t('layout.apiUnreachable')}
          </Text>
        </View>

        <Pressable onPress={i18n.toggle} style={styles.footerButton} accessibilityRole="button">
          <Icon name="globe" size={16} color={theme.colors.sidebarText} />
          <Text style={styles.footerButtonText}>
            {i18n.lang === 'en' ? 'Português' : 'English'}
          </Text>
        </Pressable>

        <Pressable onPress={toggle} style={styles.footerButton} accessibilityRole="button">
          <Icon name={isDark ? 'sun' : 'moon'} size={16} color={theme.colors.sidebarText} />
          <Text style={styles.footerButtonText}>
            {isDark ? i18n.t('layout.lightMode') : i18n.t('layout.darkMode')}
          </Text>
        </Pressable>

        <Pressable onPress={signOut} style={styles.footerButton} accessibilityRole="button">
          <Icon name="log-out" size={16} color={theme.colors.sidebarText} />
          <Text style={styles.footerButtonText}>{i18n.t('layout.signOut')}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 16,
  },
  brandMark: {
    width: 38,
    height: 38,
    borderRadius: 9999,
    backgroundColor: '#2d6a9f',
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandName: {
    color: '#ffffff',
    fontSize: 19,
    fontWeight: '700',
  },
  nav: {
    flex: 1,
  },
  navContent: {
    padding: 12,
    gap: 4,
  },
  navItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 11,
    borderRadius: 8,
  },
  navLabel: {
    fontSize: 15,
    fontWeight: '500',
    flex: 1,
  },
  navBadge: {
    backgroundColor: '#c62828',
    borderRadius: 9999,
    paddingHorizontal: 7,
    paddingVertical: 2,
  },
  navBadgeText: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: '700',
  },
  footer: {
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.08)',
    paddingHorizontal: 20,
    paddingVertical: 16,
    gap: 6,
  },
  userChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 8,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 9999,
    backgroundColor: '#2d6a9f',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 15,
  },
  userEmail: {
    color: '#c6d2e0',
    fontSize: 13,
    flex: 1,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginVertical: 6,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 9999,
    backgroundColor: '#c62828',
  },
  statusDotOnline: {
    backgroundColor: '#2e7d32',
  },
  apiStatus: {
    color: '#c6d2e0',
    fontSize: 12,
  },
  footerButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
  },
  footerButtonText: {
    color: '#c6d2e0',
    fontSize: 14,
  },
});

