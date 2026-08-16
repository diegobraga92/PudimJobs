import { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Icon, IconName } from '@/components/icons/Icon';
import { useTheme } from '@/theme/ThemeProvider';

/** Empty-state panel — mirrors the `.empty-state` class. */
export function EmptyState({
  icon = 'briefcase',
  title,
  hint,
  action,
}: {
  icon?: IconName;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  const { theme } = useTheme();
  return (
    <View
      style={[
        styles.container,
        { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
      ]}
    >
      <View style={[styles.iconWrap, { backgroundColor: theme.colors.primarySoft }]}>
        <Icon name={icon} size={26} color={theme.colors.primary} />
      </View>
      <Text style={[styles.title, { color: theme.colors.text }]}>{title}</Text>
      {hint ? <Text style={[styles.hint, { color: theme.colors.textMuted }]}>{hint}</Text> : null}
      {action ? <View style={styles.action}>{action}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    borderRadius: 12,
    borderWidth: 1,
    marginVertical: 12,
  },
  iconWrap: {
    width: 56,
    height: 56,
    borderRadius: 9999,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  title: {
    fontSize: 17,
    fontWeight: '600',
    textAlign: 'center',
  },
  hint: {
    fontSize: 14,
    textAlign: 'center',
    marginTop: 6,
    lineHeight: 20,
  },
  action: {
    marginTop: 16,
  },
});
