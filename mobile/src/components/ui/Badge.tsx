import { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';
import { ThemeColors } from '@/theme/tokens';

export type BadgeVariant = 'info' | 'warning' | 'success' | 'danger' | 'neutral';

type ColorKey = keyof ThemeColors;

const VARIANT_COLORS: Record<BadgeVariant, { fg: ColorKey; bg: ColorKey }> = {
  info: { fg: 'info', bg: 'infoSoft' },
  warning: { fg: 'warning', bg: 'warningSoft' },
  success: { fg: 'success', bg: 'successSoft' },
  danger: { fg: 'danger', bg: 'dangerSoft' },
  neutral: { fg: 'textMuted', bg: 'surfaceMuted' },
};

/** Status badge — mirrors the `.badge` (+ `-info/-warning/-success/-danger`) classes. */
export function Badge({
  variant = 'info',
  children,
}: {
  variant?: BadgeVariant;
  children: ReactNode;
}) {
  const { theme } = useTheme();
  const colors = VARIANT_COLORS[variant];
  return (
    <View style={[styles.badge, { backgroundColor: theme.colors[colors.bg] }]}>
      <Text style={[styles.text, { color: theme.colors[colors.fg] }]}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 9999,
    alignSelf: 'flex-start',
  },
  text: {
    fontSize: 12,
    fontWeight: '600',
  },
});
