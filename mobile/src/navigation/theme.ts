import {
  DarkTheme as NavDarkTheme,
  DefaultTheme as NavDefaultTheme,
  Theme as NavigationTheme,
} from '@react-navigation/native';

import { Theme } from '@/theme/tokens';

/** Maps our design tokens onto React Navigation's theme. */
export function navigationTheme(theme: Theme): NavigationTheme {
  const base = theme.dark ? NavDarkTheme : NavDefaultTheme;
  return {
    ...base,
    colors: {
      ...base.colors,
      primary: theme.colors.primary,
      background: theme.colors.bg,
      card: theme.colors.surface,
      text: theme.colors.text,
      border: theme.colors.border,
      notification: theme.colors.danger,
    },
  };
}
