import { MarkdownPanel } from "@/components/shared/markdown-panel"

interface KafkaDiagnosisProps {
  content: string
}

/**
 * Diagnosis sub-agent returns structured prose (no strict JSON schema in its
 * prompt). Render as markdown - the heading hierarchy already gives a
 * scannable layout for cluster comparison + root cause.
 */
export function KafkaDiagnosis({ content }: KafkaDiagnosisProps) {
  return <MarkdownPanel content={content} maxHClassName="max-h-[32rem]" />
}
