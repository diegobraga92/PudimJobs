import { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/components/icons/Icon';
import { useTheme } from '@/theme/ThemeProvider';

/** Top app bar with the drawer (hamburger) toggle — mobile analog of the sidebar toggle. */
export function AppHeader({
  title,
  onMenuPress,
  right,
}: {
  title: string;
  onMenuPress?: () => void;
  right?: ReactNode;
}) {
  const { theme } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[
        styles.header,
        { backgroundColor: theme.colors.surface, borderBottomColor: theme.colors.border, paddingTop: insets.top },
      ]}
    >
      <View style={styles.inner}>
        <Pressable
          onPress={onMenuPress}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel="Open navigation menu"
        >
          <Icon name="menu" size={22} color={theme.colors.text} />
        </Pressable>
        <Text style={[styles.title, { color: theme.colors.text }]} numberOfLines={1}>
          {title}
        </Text>
        <View style={styles.right}>{right}</View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    borderBottomWidth: 1,
  },
  inner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    height: 52,
    paddingHorizontal: 16,
  },
  title: {
    flex: 1,
    fontSize: 17,
    fontWeight: '700',
  },
  right: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
});
