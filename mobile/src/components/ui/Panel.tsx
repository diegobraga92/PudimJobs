import { ReactNode } from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

/** Card-like surface — mirrors the `.panel` class. */
export function Panel({
  children,
  style,
  padded = true,
}: {
  children: ReactNode;
  style?: ViewStyle;
  padded?: boolean;
}) {
  const { theme } = useTheme();
  return (
    <View
      style={[
        styles.panel,
        {
          backgroundColor: theme.colors.surface,
          borderColor: theme.colors.border,
          padding: padded ? theme.spacing.space4 : 0,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

/** `card` + `panel` combo used across the jobs/applications lists. */
export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return (
    <Panel style={style} padded={false}>
      {children}
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: {
    borderRadius: 12,
    borderWidth: 1,
  },
});
