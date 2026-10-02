/**
 * Semantic tone shared by the app-level primitives (StatusDot, StatusBadge,
 * Meter, StatTile, Callout). Maps onto the theme's severity tokens.
 *
 * Class maps are fully static so Tailwind can see every class at build time.
 */
export type Tone =
  | "success"
  | "warning"
  | "destructive"
  | "info"
  | "muted"
  | "primary"

export const TONE_TEXT: Record<Tone, string> = {
  success: "text-success",
  warning: "text-warning",
  destructive: "text-destructive",
  info: "text-info",
  muted: "text-muted-foreground",
  primary: "text-primary",
}

export const TONE_BG: Record<Tone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  destructive: "bg-destructive",
  info: "bg-info",
  muted: "bg-muted-foreground/60",
  primary: "bg-primary",
}

export const TONE_TINT: Record<Tone, string> = {
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  destructive: "bg-destructive/15 text-destructive",
  info: "bg-info/15 text-info",
  muted: "bg-muted text-muted-foreground",
  primary: "bg-primary/15 text-primary",
}
