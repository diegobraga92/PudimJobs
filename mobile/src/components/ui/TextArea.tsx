import { StyleSheet, TextInput, TextInputProps } from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

/** Multi-line text input — mirrors the `.textarea` class. */
export function TextArea(props: TextInputProps & { minHeight?: number }) {
  const { theme } = useTheme();
  const { minHeight = 80, style, ...rest } = props;
  return (
    <TextInput
      placeholderTextColor={theme.colors.textFaint}
      multiline
      textAlignVertical="top"
      {...rest}
      style={[
        styles.textarea,
        {
          backgroundColor: theme.colors.surface,
          borderColor: theme.colors.border,
          color: theme.colors.text,
          minHeight,
        },
        style,
      ]}
    />
  );
}

const styles = StyleSheet.create({
  textarea: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
});
