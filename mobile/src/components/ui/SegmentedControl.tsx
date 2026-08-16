import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ReactNode } from 'react';
import { useTheme } from '@/theme/ThemeProvider';

export interface SegmentedOption<T extends string = string> {
  label: string;
  value: T;
  icon?: ReactNode;
}

/** Segmented control — mirrors the CV editor's Edit / Preview tabs. */
export function SegmentedControl<T extends string = string>({
  options,
  value,
  onChange,
}: {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
}) {
  const { theme } = useTheme();
  return (
    <View
      style={[
        styles.container,
        { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border },
      ]}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <Pressable
            key={option.value}
            onPress={() => onChange(option.value)}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            style={({ pressed }) => [
              styles.tab,
              active
                ? { backgroundColor: theme.colors.surface, borderColor: theme.colors.borderStrong }
                : { backgroundColor: 'transparent', borderColor: 'transparent' },
              pressed && !active ? { backgroundColor: theme.colors.border } : null,
            ]}
          >
            {option.icon ? <View style={styles.icon}>{option.icon}</View> : null}
            <Text
              style={[
                styles.label,
                { color: active ? theme.colors.primary : theme.colors.textMuted },
              ]}
            >
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    borderRadius: 10,
    borderWidth: 1,
    padding: 3,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
  },
  icon: {
    marginRight: 2,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
  },
});
