import { ScreenPlaceholder } from '@/components/ScreenPlaceholder';
import { useI18n } from '@/i18n/I18nProvider';

export function NotificationsScreen() {
  const i18n = useI18n();
  return <ScreenPlaceholder title={i18n.t('notifications.title')} icon="bell-ring" />;
}
