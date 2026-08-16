/**
 * PudimJobs Design Tokens — React Native port of the web design system
 * (frontend/src/styles.scss). Colors mirror the CSS custom properties 1:1,
 * including the `[data-theme='dark']` overrides.
 */

export interface ThemeColors {
  primary: string;
  primaryHover: string;
  primaryActive: string;
  primarySoft: string;
  accent: string;
  accentHover: string;

  bg: string;
  surface: string;
  surfaceMuted: string;
  border: string;
  borderStrong: string;

  text: string;
  textSecondary: string;
  textMuted: string;
  textFaint: string;

  success: string;
  successSoft: string;
  successSoftHover: string;
  warning: string;
  warningSoft: string;
  danger: string;
  dangerSoft: string;
  info: string;
  infoSoft: string;

  onPrimary: string;

  sidebarBg: string;
  sidebarText: string;
  sidebarHover: string;
  sidebarActive: string;

  kanbanColumn: string;
  skeleton: string;
  flaggedRow: string;
  unreadBg: string;
}

export const lightColors: ThemeColors = {
  primary: '#1e3a5f',
  primaryHover: '#264a78',
  primaryActive: '#16294a',
  primarySoft: '#e3f0fa',
  accent: '#2d6a9f',
  accentHover: '#357cb8',

  bg: '#f5f6f8',
  surface: '#ffffff',
  surfaceMuted: '#f8f9fb',
  border: '#e2e5ea',
  borderStrong: '#c9ced6',

  text: '#1f2430',
  textSecondary: '#4a5568',
  textMuted: '#6b7280',
  textFaint: '#9aa1ac',

  success: '#2e7d32',
  successSoft: '#e8f5e9',
  successSoftHover: '#d9efdb',
  warning: '#b45309',
  warningSoft: '#fef3c7',
  danger: '#c62828',
  dangerSoft: '#ffebee',
  info: '#1e56a0',
  infoSoft: '#e3f0fa',

  onPrimary: '#ffffff',

  sidebarBg: '#14263d',
  sidebarText: '#c6d2e0',
  sidebarHover: 'rgba(255, 255, 255, 0.08)',
  sidebarActive: '#2d6a9f',

  kanbanColumn: '#e9edf2',
  skeleton: '#e7eaf0',
  flaggedRow: '#fff8e1',
  unreadBg: '#fbfdff',
};

export const darkColors: ThemeColors = {
  primary: '#4d8bc0',
  primaryHover: '#5d9bd0',
  primaryActive: '#3a6f9c',
  primarySoft: '#1c3145',
  accent: '#5da3d8',
  accentHover: '#6db3e8',

  bg: '#0e1521',
  surface: '#16202f',
  surfaceMuted: '#1c2939',
  border: '#27364c',
  borderStrong: '#3a4d69',

  text: '#e8edf5',
  textSecondary: '#b8c4d6',
  textMuted: '#8c99ae',
  textFaint: '#66748c',

  success: '#7bd88b',
  successSoft: '#14301c',
  successSoftHover: '#1d3f26',
  warning: '#ffca7a',
  warningSoft: '#3a2e12',
  danger: '#ff8a80',
  dangerSoft: '#3a1c1c',
  info: '#6bb8ff',
  infoSoft: '#16314d',

  onPrimary: '#ffffff',

  sidebarBg: '#0a111c',
  sidebarText: '#aebdd2',
  sidebarHover: 'rgba(255, 255, 255, 0.07)',
  sidebarActive: '#2c5f8f',

  kanbanColumn: '#101a28',
  skeleton: '#223044',
  flaggedRow: '#33291a',
  unreadBg: '#14212f',
};

/** Fixed design scale (shared by light + dark). */
export const spacing = {
  space1: 4,
  space2: 8,
  space3: 12,
  space4: 16,
  space5: 20,
  space6: 24,
  space8: 32,
  space10: 40,
  space12: 48,
  space16: 64,
} as const;

export const radii = {
  sm: 6,
  md: 8,
  lg: 12,
  xl: 16,
  full: 9999,
} as const;

export const typography = {
  textXs: 12,
  textSm: 13,
  textBase: 15,
  textLg: 17,
  textXl: 20,
  text2xl: 24,
  text3xl: 30,
  weightNormal: '400',
  weightMedium: '500',
  weightSemibold: '600',
  weightBold: '700',
} as const;

export const shadows = {
  xs: {
    elevation: 1,
    shadowColor: '#0f172a',
    shadowOpacity: 0.06,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
  },
  sm: {
    elevation: 2,
    shadowColor: '#0f172a',
    shadowOpacity: 0.08,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
  },
  md: {
    elevation: 4,
    shadowColor: '#0f172a',
    shadowOpacity: 0.08,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  lg: {
    elevation: 8,
    shadowColor: '#0f172a',
    shadowOpacity: 0.14,
    shadowRadius: 32,
    shadowOffset: { width: 0, height: 10 },
  },
  cardHover: {
    elevation: 6,
    shadowColor: '#0f172a',
    shadowOpacity: 0.12,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
  },
} as const;

export interface Theme {
  dark: boolean;
  colors: ThemeColors;
  spacing: typeof spacing;
  radii: typeof radii;
  typography: typeof typography;
  shadows: typeof shadows;
  /** Status bar / navigation bar color (mirrors the web <meta theme-color>). */
  chromeColor: string;
}

export function createTheme(dark: boolean): Theme {
  return {
    dark,
    colors: dark ? darkColors : lightColors,
    spacing,
    radii,
    typography,
    shadows,
    chromeColor: dark ? '#0a111c' : '#1e3a5f',
  };
}
