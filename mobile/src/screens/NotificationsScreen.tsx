import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Icon } from '@/components/icons/Icon';
import { useToast } from '@/components/toast/ToastProvider';
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from '@/hooks/useNotifications';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { Notification } from '@/types';
import { dateLocale, shortDate } from '@/utils/dates';

/** Notifications inbox — mirrors the web notifications page. */
export function NotificationsScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const { data, isPending, error } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const notifications = data?.items ?? [];
  const unread = data?.unread ?? 0;
  const total = data?.total ?? 0;

  const onMarkRead = (notification: Notification) => {
    markRead.mutate(notification.id, {
      onError: () => toast.error(i18n.t('errors.failedUpdateNotification')),
    });
  };

  const onMarkAllRead = () => {
    markAllRead.mutate(undefined, {
      onSuccess: () => toast.success(i18n.t('notifications.allReadToast')),
      onError: () => toast.error(i18n.t('errors.failedUpdateNotifications')),
    });
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.bg }]}
      contentContainerStyle={styles.content}
    >
      <View style={styles.head}>
        <Text style={[styles.title, { color: theme.colors.text }]}>
          {i18n.t('notifications.title')}
        </Text>
        <Button variant="ghost" size="sm" onPress={onMarkAllRead} disabled={unread === 0}>
          <Icon name="check" size={15} />
          {i18n.t('notifications.markAllRead')}
        </Button>
      </View>

      {error ? <Alert tone="error">{i18n.t('errors.failedLoadNotifications')}</Alert> : null}

      <View style={styles.summary}>
        {unread > 0 ? (
          <Badge variant="info">{i18n.t('notifications.unread', { count: unread })}</Badge>
        ) : null}
        <Text style={[styles.muted, { color: theme.colors.textMuted }]}>
          {i18n.t('notifications.total', { count: total })}
        </Text>
      </View>

      {!isPending && notifications.length === 0 ? (
        <EmptyState
          icon="inbox"
          title={i18n.t('notifications.emptyTitle')}
          hint={i18n.t('notifications.emptyHint')}
        />
      ) : null}

      {notifications.map((item) => (
        <View
          key={item.id}
          style={[
            styles.item,
            {
              backgroundColor: item.read ? theme.colors.surface : theme.colors.unreadBg,
              borderColor: theme.colors.border,
            },
          ]}
        >
          <View
            style={[
              styles.unreadDot,
              { backgroundColor: item.read ? 'transparent' : theme.colors.primary },
            ]}
          />
          <View style={styles.itemMain}>
            <Text style={[styles.itemTitle, { color: theme.colors.text }]}>{item.title}</Text>
            {item.message ? (
              <Text style={[styles.itemMessage, { color: theme.colors.textSecondary }]}>
                {item.message}
              </Text>
            ) : null}
            <View style={styles.itemMeta}>
              <Icon name="bell" size={12} color={theme.colors.textFaint} />
              <Text style={[styles.metaText, { color: theme.colors.textMuted }]}>
                {item.channel} · {shortDate(item.created_at, dateLocale(i18n.lang))} · {item.status}
              </Text>
            </View>
          </View>
          {!item.read ? (
            <Button variant="ghost" size="sm" onPress={() => onMarkRead(item)}>
              {i18n.t('notifications.markRead')}
            </Button>
          ) : null}
        </View>
      ))}
    </ScrollView>
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
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
  },
  summary: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  muted: {
    fontSize: 13,
  },
  item: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
    marginBottom: 10,
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 9999,
    marginTop: 5,
  },
  itemMain: {
    flex: 1,
    gap: 3,
  },
  itemTitle: {
    fontSize: 15,
    fontWeight: '600',
  },
  itemMessage: {
    fontSize: 14,
    lineHeight: 20,
  },
  itemMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginTop: 2,
  },
  metaText: {
    fontSize: 12,
  },
});
