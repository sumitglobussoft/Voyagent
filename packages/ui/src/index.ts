/**
 * @voyagent/ui — primitive React components.
 *
 * These are dependency-light, Tailwind-styled, ref-forwarding building
 * blocks consumed by `apps/web` and `apps/desktop`. Mobile will get its
 * own Tamagui-backed implementation later; do not import this package
 * from React Native.
 *
 * Every component accepts `className` for consumer overrides and forwards
 * a ref to the underlying DOM element.
 */
export { Button } from "./Button.js";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./Button.js";

export { Input } from "./Input.js";
export type { InputProps } from "./Input.js";

export { Card } from "./Card.js";
export type { CardProps } from "./Card.js";

export { EmptyState } from "./EmptyState.js";
export type { EmptyStateProps } from "./EmptyState.js";

export { Spinner } from "./Spinner.js";
export type { SpinnerProps, SpinnerSize } from "./Spinner.js";

export { Badge } from "./Badge.js";
export type { BadgeProps, BadgeVariant } from "./Badge.js";

export { Stack } from "./Stack.js";
export type {
  StackProps,
  StackDirection,
  StackGap,
  StackAlign,
  StackJustify,
} from "./Stack.js";

export { TextArea } from "./TextArea.js";
export type { TextAreaProps } from "./TextArea.js";

export { Avatar } from "./Avatar.js";
export type { AvatarProps, AvatarSize } from "./Avatar.js";

export { cn } from "./cn.js";
