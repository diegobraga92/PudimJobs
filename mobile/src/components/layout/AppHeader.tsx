import { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/components/icons/Icon';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';

/**
 * Top app bar. With `back` it shows a back arrow (used on pushed detail
 * screens); otherwise it shows the drawer (hamburger) toggle — the mobile
 * analog of the web sidebar toggle.
 */
export function AppHeader({
  title,
  onLeftPress,
  right,
  back = false,
}: {
  title: string;
  onLeftPress?: () => void;
  right?: ReactNode;
  back?: boolean;
}) {
  const { theme } = useTheme();
  const i18n = useI18n();
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
          onPress={onLeftPress}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel={back ? i18n.t('jobDetail.backToJobs') : i18n.t('layout.aria.openNav')}
        >
          <Icon name={back ? 'arrow-left' : 'menu'} size={22} color={theme.colors.text} />
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
