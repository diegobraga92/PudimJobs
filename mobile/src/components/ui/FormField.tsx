import { ReactNode } from 'react';
import { StyleSheet, Text, View, ViewStyle } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

/** Form field wrapper with label + optional error — mirrors `.form-field`. */
export function FormField({
  label,
  error,
  children,
  style,
}: {
  label?: string;
  error?: string | null;
  children: ReactNode;
  style?: ViewStyle;
}) {
  const { theme } = useTheme();
  return (
    <View style={[styles.field, style]}>
      {label ? <Text style={[styles.label, { color: theme.colors.text }]}>{label}</Text> : null}
      {children}
      {error ? <Text style={[styles.error, { color: theme.colors.danger }]}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  field: {
    marginBottom: 14,
  },
  label: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 6,
  },
  error: {
    fontSize: 12,
    marginTop: 4,
  },
});
