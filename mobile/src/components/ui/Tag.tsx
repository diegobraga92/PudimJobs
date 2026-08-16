import { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

/** Small pill used for job tags, skills, keywords — mirrors the `.tag` class. */
export function Tag({ children }: { children: ReactNode }) {
  const { theme } = useTheme();
  return (
    <View
      style={[
        styles.tag,
        { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border },
      ]}
    >
      <Text style={[styles.text, { color: theme.colors.textSecondary }]}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tag: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 9999,
    borderWidth: 1,
  },
  text: {
    fontSize: 12,
    fontWeight: '500',
  },
});
