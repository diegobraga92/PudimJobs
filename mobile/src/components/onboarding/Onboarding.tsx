import { StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { Icon, IconName } from '@/components/icons/Icon';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';

interface OnboardingStep {
  icon: IconName;
  titleKey: string;
  descriptionKey: string;
  ctaKey: string;
}

const STEPS: OnboardingStep[] = [
  {
    icon: 'globe',
    titleKey: 'onboarding.step1.title',
    descriptionKey: 'onboarding.step1.description',
    ctaKey: 'onboarding.step1.cta',
  },
  {
    icon: 'file-text',
    titleKey: 'onboarding.step2.title',
    descriptionKey: 'onboarding.step2.description',
    ctaKey: 'onboarding.step2.cta',
  },
  {
    icon: 'kanban',
    titleKey: 'onboarding.step3.title',
    descriptionKey: 'onboarding.step3.description',
    ctaKey: 'onboarding.step3.cta',
  },
];

/** First-run welcome panel — mirrors the web `app-onboarding` component. */
export function Onboarding({ onDismiss }: { onDismiss: () => void }) {
  const { theme } = useTheme();
  const i18n = useI18n();

  return (
    <View
      style={[
        styles.panel,
        { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
      ]}
    >
      <View style={styles.head}>
        <View style={[styles.headIcon, { backgroundColor: theme.colors.primarySoft }]}>
          <Icon name="sparkle" size={26} color={theme.colors.primary} />
        </View>
        <View style={styles.headText}>
          <Text style={[styles.headTitle, { color: theme.colors.primary }]}>
            {i18n.t('onboarding.welcome')}
          </Text>
          <Text style={[styles.headSub, { color: theme.colors.textMuted }]}>
            {i18n.t('onboarding.intro')}
          </Text>
        </View>
      </View>

      <View style={styles.steps}>
        {STEPS.map((step) => (
          <View
            key={step.ctaKey}
            style={[
              styles.step,
              { borderColor: theme.colors.border, backgroundColor: theme.colors.surfaceMuted },
            ]}
          >
            <View
              style={[
                styles.stepIcon,
                { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
              ]}
            >
              <Icon name={step.icon} size={20} color={theme.colors.accent} />
            </View>
            <View style={styles.stepBody}>
              <Text style={[styles.stepTitle, { color: theme.colors.text }]}>
                {i18n.t(step.titleKey)}
              </Text>
              <Text style={[styles.stepDesc, { color: theme.colors.textMuted }]}>
                {i18n.t(step.descriptionKey)}
              </Text>
            </View>
            <Button variant="ghost" size="sm" onPress={onDismiss}>
              {i18n.t(step.ctaKey)}
            </Button>
          </View>
        ))}
      </View>

      <View style={styles.foot}>
        <Button variant="ghost" onPress={onDismiss}>
          {i18n.t('onboarding.dismiss')}
        </Button>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
    marginBottom: 16,
  },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 12,
  },
  headIcon: {
    width: 52,
    height: 52,
    borderRadius: 9999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headText: {
    flex: 1,
  },
  headTitle: {
    fontSize: 20,
    fontWeight: '700',
  },
  headSub: {
    fontSize: 14,
    marginTop: 2,
  },
  steps: {
    gap: 8,
  },
  step: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  stepIcon: {
    width: 40,
    height: 40,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepBody: {
    flex: 1,
  },
  stepTitle: {
    fontSize: 15,
    fontWeight: '600',
  },
  stepDesc: {
    fontSize: 13,
    marginTop: 1,
  },
  foot: {
    alignItems: 'flex-end',
    marginTop: 12,
  },
});
