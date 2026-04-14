/**
 * @voyagent/icons — curated re-exports from `lucide-react`.
 *
 * We wrap Lucide rather than letting each app import from it directly so
 * that:
 *   1. The Voyagent UI surfaces share one visual vocabulary.
 *   2. Consumers see a small, discoverable icon catalogue instead of
 *      Lucide's thousand-plus glyphs.
 *   3. Bundlers can tree-shake aggressively because the re-export surface
 *      is explicit and named.
 *
 * To add a new icon, find its PascalCase name in the Lucide catalog
 * (https://lucide.dev/icons) and append it below — one line, done.
 *
 * Every re-export preserves Lucide's own type signature (`LucideIcon`);
 * consumers get full prop typings including `size`, `color`, `strokeWidth`
 * and standard SVG props.
 */
export {
  Plane,
  Hotel,
  Calculator,
  Send,
  Check,
  X,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Menu,
  Search,
  User,
  Users,
  Settings,
  LogOut,
  FileText,
  CreditCard,
  Receipt,
  RefreshCcw,
  Paperclip,
  Download,
  Upload,
  Copy,
  Loader2,
} from "lucide-react";

export type { LucideIcon, LucideProps } from "lucide-react";
