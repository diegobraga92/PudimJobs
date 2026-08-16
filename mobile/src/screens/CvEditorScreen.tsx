import { ScreenPlaceholder } from '@/components/ScreenPlaceholder';
import { useI18n } from '@/i18n/I18nProvider';

export function CvEditorScreen() {
  const i18n = useI18n();
  return <ScreenPlaceholder title={i18n.t('cv.title')} icon="file-text" />;
}
