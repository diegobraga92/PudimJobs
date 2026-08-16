import { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Icon, IconName } from '@/components/icons/Icon';
import { useTheme } from '@/theme/ThemeProvider';
import { ThemeColors } from '@/theme/tokens';

export type AlertTone = 'error' | 'success' | 'warning' | 'info';

type ColorKey = keyof ThemeColors;

const TONE_ICON: Record<AlertTone, IconName> = {
  error: 'circle-alert',
  success: 'circle-check',
  warning: 'triangle-alert',
  info: 'info',
};

const TONE_COLORS: Record<AlertTone, { fg: ColorKey; bg: ColorKey }> = {
  error: { fg: 'danger', bg: 'dangerSoft' },
  success: { fg: 'success', bg: 'successSoft' },
  warning: { fg: 'warning', bg: 'warningSoft' },
  info: { fg: 'info', bg: 'infoSoft' },
};

/** Inline alert banner — mirrors the `.alert` / `.alert-error` / `.alert-success` classes. */
export function Alert({
  tone = 'info',
  children,
}: {
  tone?: AlertTone;
  children: ReactNode;
}) {
  const { theme } = useTheme();
  const colors = TONE_COLORS[tone];
  return (
    <View style={[styles.alert, { backgroundColor: theme.colors[colors.bg] }]}>
      <Icon name={TONE_ICON[tone]} size={18} color={theme.colors[colors.fg]} />
      <Text style={[styles.text, { color: theme.colors[colors.fg] }]}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  alert: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
    marginVertical: 8,
  },
  text: {
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
});
