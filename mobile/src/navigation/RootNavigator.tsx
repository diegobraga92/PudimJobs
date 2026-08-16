import { NavigationContainer } from '@react-navigation/native';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';
import { useAuthStore } from '@/store/auth';
import { AppDrawer } from './AppDrawer';
import { AuthStack } from './AuthStack';
import { navigationTheme } from './theme';

/**
 * Root navigator — switches between the Auth stack and the app drawer based on
 * the presence of a JWT (mirrors the web authGuard). Renders a splash until the
 * secure store has rehydrated so we never flash the wrong screen.
 */
export function RootNavigator() {
  const { theme } = useTheme();
  const token = useAuthStore((state) => state.token);
  const hasHydrated = useAuthStore((state) => state.hasHydrated);

  if (!hasHydrated) {
    return (
      <View style={[styles.splash, { backgroundColor: theme.colors.bg }]}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }

  return (
    <NavigationContainer theme={navigationTheme(theme)}>
      {token ? <AppDrawer /> : <AuthStack />}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
