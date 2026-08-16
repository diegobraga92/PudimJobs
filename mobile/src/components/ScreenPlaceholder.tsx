import { StyleSheet, Text, View } from 'react-native';

import { Icon, IconName } from '@/components/icons/Icon';
import { useTheme } from '@/theme/ThemeProvider';

/** Temporary stand-in for screens that are not implemented yet. */
export function ScreenPlaceholder({ title, icon }: { title: string; icon: IconName }) {
  const { theme } = useTheme();
  return (
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <View style={[styles.card, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
        <Icon name={icon} size={28} color={theme.colors.textMuted} />
        <Text style={[styles.title, { color: theme.colors.text }]}>{title}</Text>
        <Text style={[styles.hint, { color: theme.colors.textMuted }]}>
          This screen is coming next — it will mirror the web UI.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  card: {
    alignItems: 'center',
    gap: 10,
    padding: 32,
    borderRadius: 12,
    borderWidth: 1,
    maxWidth: 360,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  hint: {
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 20,
  },
});
