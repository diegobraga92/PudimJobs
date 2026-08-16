import {
  Activity,
  ArrowLeft,
  Bell,
  BellRing,
  Briefcase,
  Calendar,
  ChartColumn,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FilePlus,
  FileText,
  Globe,
  House,
  Inbox,
  Info,
  Kanban,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  LogOut,
  Mail,
  MapPin,
  Menu,
  Moon,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Star,
  Sun,
  TimerReset,
  Trash,
  TriangleAlert,
  User,
  Wand,
  X,
  type LucideIcon,
} from 'lucide-react-native';

import { useTheme } from '@/theme/ThemeProvider';

/**
 * Icon names — mirrors the web `AppIconName` registry plus a few extras used
 * by the mobile shell (chevron-down, menu, arrow-left, …).
 */
export type IconName =
  | 'activity'
  | 'arrow-left'
  | 'bell'
  | 'bell-ring'
  | 'briefcase'
  | 'calendar'
  | 'check'
  | 'chart'
  | 'chevron-down'
  | 'chevron-left'
  | 'chevron-right'
  | 'circle-alert'
  | 'circle-check'
  | 'clock'
  | 'copy'
  | 'download'
  | 'external-link'
  | 'eye'
  | 'eye-off'
  | 'file-plus'
  | 'file-text'
  | 'globe'
  | 'home'
  | 'history'
  | 'inbox'
  | 'info'
  | 'kanban'
  | 'layout-dashboard'
  | 'list-filter'
  | 'loader'
  | 'log-out'
  | 'mail'
  | 'map-pin'
  | 'menu'
  | 'moon'
  | 'pencil'
  | 'plus'
  | 'refresh'
  | 'search'
  | 'send'
  | 'settings'
  | 'shield-check'
  | 'sparkle'
  | 'star'
  | 'sun'
  | 'trash'
  | 'triangle-alert'
  | 'user'
  | 'wand'
  | 'x';

const ICONS: Record<IconName, LucideIcon> = {
  activity: Activity,
  'arrow-left': ArrowLeft,
  bell: Bell,
  'bell-ring': BellRing,
  briefcase: Briefcase,
  calendar: Calendar,
  check: Check,
  chart: ChartColumn,
  'chevron-down': ChevronDown,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  'circle-alert': CircleAlert,
  'circle-check': CircleCheck,
  clock: Clock,
  copy: Copy,
  download: Download,
  'external-link': ExternalLink,
  eye: Eye,
  'eye-off': EyeOff,
  'file-plus': FilePlus,
  'file-text': FileText,
  globe: Globe,
  home: House,
  history: TimerReset,
  inbox: Inbox,
  info: Info,
  kanban: Kanban,
  'layout-dashboard': LayoutDashboard,
  'list-filter': ListFilter,
  loader: LoaderCircle,
  'log-out': LogOut,
  mail: Mail,
  'map-pin': MapPin,
  menu: Menu,
  moon: Moon,
  pencil: Pencil,
  plus: Plus,
  refresh: RefreshCw,
  search: Search,
  send: Send,
  settings: Settings,
  'shield-check': ShieldCheck,
  sparkle: Sparkles,
  star: Star,
  sun: Sun,
  trash: Trash,
  'triangle-alert': TriangleAlert,
  user: User,
  wand: Wand,
  x: X,
};

export interface IconProps {
  name: IconName;
  size?: number;
  /** Defaults to the current theme's primary text color (CSS `currentColor` analog). */
  color?: string;
  strokeWidth?: number;
}

/**
 * Inline icon renderer — the React Native analog of the web `app-icon`
 * component. Defaults to the theme text color so callers only pass `color`
 * when they need to deviate.
 */
export function Icon({ name, size = 20, color, strokeWidth = 2 }: IconProps) {
  const { theme } = useTheme();
  const resolvedColor = color ?? theme.colors.text;
  const Lucide = ICONS[name];
  return <Lucide width={size} height={size} size={size} color={resolvedColor} strokeWidth={strokeWidth} />;
}
