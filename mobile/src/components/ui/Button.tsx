import { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, ViewStyle } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

export type ButtonVariant = 'primary' | 'ghost' | 'danger' | 'dangerSolid' | 'accent' | 'success';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps {
  onPress?: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
  fullWidth?: boolean;
  accessibilityLabel?: string;
  style?: ViewStyle;
}

/** Button — mirrors the `.btn` family (`btn-primary/ghost/danger/accent/success`, sizes). */
export function Button({
  onPress,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  icon,
  children,
  fullWidth = false,
  accessibilityLabel,
  style,
}: ButtonProps) {
  const { theme } = useTheme();

  const backgroundColor =
    variant === 'primary'
      ? theme.colors.primary
      : variant === 'accent'
        ? theme.colors.accent
        : variant === 'dangerSolid'
          ? theme.colors.danger
          : variant === 'success'
            ? theme.colors.success
            : 'transparent';

  const foreground =
    variant === 'primary' || variant === 'dangerSolid' || variant === 'success'
      ? theme.colors.onPrimary
      : variant === 'accent'
        ? theme.colors.onPrimary
        : theme.colors.text;

  const borderColor =
    variant === 'ghost' || variant === 'danger'
      ? theme.colors.borderStrong
      : backgroundColor;

  const pressedBg =
    variant === 'primary'
      ? theme.colors.primaryHover
      : variant === 'accent'
        ? theme.colors.accentHover
        : variant === 'ghost' || variant === 'danger'
          ? theme.colors.surfaceMuted
          : backgroundColor;

  const height = size === 'sm' ? 32 : size === 'lg' ? 48 : 40;
  const fontSize = size === 'sm' ? 13 : size === 'lg' ? 16 : 14;

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      style={({ pressed }) => [
        styles.base,
        {
          backgroundColor: pressed ? pressedBg : backgroundColor,
          borderColor,
          height,
          minWidth: size === 'sm' ? 64 : 96,
          paddingHorizontal: size === 'sm' ? 12 : 16,
        },
        fullWidth ? styles.fullWidth : null,
        (disabled || loading) ? { opacity: 0.55 } : null,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator
          size="small"
          color={variant === 'ghost' || variant === 'danger' ? theme.colors.text : theme.colors.onPrimary}
        />
      ) : icon ? (
        icon
      ) : null}
      {children ? (
        <Text style={[styles.label, { color: foreground, fontSize, fontWeight: size === 'sm' ? '500' : '600' }]}>
          {children}
        </Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 8,
    borderWidth: 1,
  },
  fullWidth: {
    alignSelf: 'stretch',
  },
  label: {
    textAlign: 'center',
  },
});
