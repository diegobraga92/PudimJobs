import { Switch as RNSwitch, SwitchProps } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

/** Themed switch — mirrors the web checkboxes used for filters/toggles. */
export function Switch({ ...props }: SwitchProps) {
  const { theme } = useTheme();
  return (
    <RNSwitch
      thumbColor={theme.colors.onPrimary}
      trackColor={{
        false: theme.colors.borderStrong,
        true: theme.colors.primary,
      }}
      ios_backgroundColor={theme.colors.borderStrong}
      {...props}
    />
  );
}
