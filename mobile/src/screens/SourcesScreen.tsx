import { ScreenPlaceholder } from '@/components/ScreenPlaceholder';
import { useI18n } from '@/i18n/I18nProvider';

export function SourcesScreen() {
  const i18n = useI18n();
  return <ScreenPlaceholder title={i18n.t('sources.title')} icon="globe" />;
}
