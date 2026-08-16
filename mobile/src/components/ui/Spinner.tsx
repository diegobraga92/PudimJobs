import { ActivityIndicator } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

export function Spinner({ size = 'small', color }: { size?: 'small' | 'large'; color?: string }) {
  const { theme } = useTheme();
  return <ActivityIndicator size={size} color={color ?? theme.colors.primary} />;
}
