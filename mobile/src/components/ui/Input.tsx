import { forwardRef } from 'react';
import {
  KeyboardTypeOptions,
  Pressable,
  StyleSheet,
  TextInput,
  TextInputProps,
  View,
} from 'react-native';

import { Icon } from '@/components/icons/Icon';
import { useTheme } from '@/theme/ThemeProvider';

interface InputProps extends TextInputProps {
  /** Renders a password toggle on the right (mirrors `login.component.html`). */
  passwordToggle?: boolean;
  showPassword?: boolean;
  onTogglePassword?: () => void;
}

/** Text input — mirrors the `.input` class with optional password reveal. */
export const Input = forwardRef<TextInput, InputProps>(function Input(
  { passwordToggle = false, showPassword, onTogglePassword, style, ...props },
  ref,
) {
  const { theme } = useTheme();
  return (
    <View style={styles.wrap}>
      <TextInput
        ref={ref}
        placeholderTextColor={theme.colors.textFaint}
        {...props}
        secureTextEntry={props.secureTextEntry ?? (passwordToggle ? !showPassword : undefined)}
        style={[
          styles.input,
          {
            backgroundColor: theme.colors.surface,
            borderColor: theme.colors.border,
            color: theme.colors.text,
          },
          passwordToggle ? styles.inputWithToggle : null,
          style,
        ]}
      />
      {passwordToggle ? (
        <Pressable
          onPress={onTogglePassword}
          accessibilityRole="button"
          accessibilityLabel={showPassword ? 'hide-password' : 'show-password'}
          hitSlop={8}
          style={styles.toggle}
        >
          <Icon name={showPassword ? 'eye-off' : 'eye'} size={18} color={theme.colors.textMuted} />
        </Pressable>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  wrap: {
    position: 'relative',
  },
  input: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  inputWithToggle: {
    paddingRight: 44,
  },
  toggle: {
    position: 'absolute',
    right: 12,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
  },
});

export type { KeyboardTypeOptions };
