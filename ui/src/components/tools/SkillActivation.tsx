import { BookOpen } from "lucide-react"
import { MarkdownPanel } from "@/components/shared/markdown-panel"
import { extractSkillName } from "./tool-styles"

interface SkillActivationProps {
  input: unknown
  content: string
}

/** Strips the YAML frontmatter from a SKILL.md, returning just the body. */
function splitFrontmatter(md: string): { frontmatter: string | null; body: string } {
  if (!md.startsWith("---")) return { frontmatter: null, body: md }
  const end = md.indexOf("\n---", 3)
  if (end === -1) return { frontmatter: null, body: md }
  return {
    frontmatter: md.slice(3, end).trim(),
    body: md.slice(end + 4).replace(/^\n/, ""),
  }
}

/** Best-effort scan of YAML frontmatter for a `description:` line. */
function parseDescription(frontmatter: string | null): string | null {
  if (!frontmatter) return null
  const match = frontmatter.match(/^description:\s*(.+)$/m)
  return match ? match[1].trim() : null
}

export function SkillActivation({ input, content }: SkillActivationProps) {
  const skillName = extractSkillName(input)
  const { frontmatter, body } = splitFrontmatter(content)
  const description = parseDescription(frontmatter)

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm">
        <BookOpen className="size-4 text-warning shrink-0" />
        <span className="font-medium">Activated skill:</span>
        <span className="font-mono text-warning">{skillName ?? "(unknown)"}</span>
      </div>
      {description && (
        <div className="text-xs text-muted-foreground leading-snug">{description}</div>
      )}
      <MarkdownPanel content={body || content} maxHClassName="max-h-[28rem]" />
    </div>
  )
}
