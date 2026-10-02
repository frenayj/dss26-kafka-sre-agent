import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"

interface MarkdownProps {
  content: string
  className?: string
  /** `compact` (default) - typeset chat prose for in-card rendering
   *  (see src/typeset.css + the `typeset-chat` preset in index.css).
   *  `document` - generous A4-page prose on a white background. */
  variant?: "compact" | "document"
}

/** Wide GFM tables scroll inside their own box instead of squeezing the
 *  column. `typeset-scroll` owns the flow margin and is append-safe while
 *  streaming (no-op in the document variant, which has no typeset scope). */
const mdComponents: Components = {
  table: (props) => {
    const { node, ...rest } = props
    void node
    return (
      <div className="typeset-scroll">
        <table {...rest} />
      </div>
    )
  },
}

// Black ink on white paper. Sized for printing/reading as a standalone
// document, not as a card cell. Mimics Confluence/Notion page typography.
const documentStyles = [
  "text-[15px] leading-7 text-gray-900 font-sans",
  "[&_h1]:text-3xl [&_h1]:font-semibold [&_h1]:mt-0 [&_h1]:mb-6 [&_h1]:text-gray-900 [&_h1]:tracking-tight",
  "[&_h2]:text-xl [&_h2]:font-semibold [&_h2]:mt-8 [&_h2]:mb-3 [&_h2]:text-gray-900 [&_h2]:tracking-tight",
  "[&_h3]:text-base [&_h3]:font-semibold [&_h3]:mt-6 [&_h3]:mb-2 [&_h3]:text-gray-900",
  "[&_h4]:text-sm [&_h4]:font-semibold [&_h4]:mt-4 [&_h4]:mb-2 [&_h4]:text-gray-800 [&_h4]:uppercase [&_h4]:tracking-wider",
  "[&_p]:my-3 [&_p]:text-gray-800",
  "[&_strong]:text-gray-900 [&_strong]:font-semibold",
  "[&_em]:text-gray-800",
  "[&_ul]:my-3 [&_ul]:pl-6 [&_ul]:list-disc [&_ul]:marker:text-gray-400",
  "[&_ol]:my-3 [&_ol]:pl-6 [&_ol]:list-decimal [&_ol]:marker:text-gray-400",
  "[&_li]:my-1 [&_li]:text-gray-800 [&_li]:pl-1",
  "[&_code]:font-mono [&_code]:text-[13px] [&_code]:bg-gray-100 [&_code]:text-gray-900 [&_code]:rounded [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:border [&_code]:border-gray-200",
  "[&_pre]:bg-gray-50 [&_pre]:border [&_pre]:border-gray-200 [&_pre]:p-4 [&_pre]:rounded-md [&_pre]:overflow-auto [&_pre]:my-4 [&_pre]:text-[13px] [&_pre]:leading-6",
  "[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:border-0",
  "[&_a]:text-blue-700 [&_a]:underline [&_a]:underline-offset-2 [&_a]:hover:text-blue-900",
  "[&_table]:my-4 [&_table]:text-sm [&_table]:w-full [&_table]:border-collapse [&_table]:border [&_table]:border-gray-200",
  "[&_thead]:bg-gray-50",
  "[&_th]:text-left [&_th]:py-2 [&_th]:px-3 [&_th]:border-b [&_th]:border-gray-200 [&_th]:font-semibold [&_th]:text-gray-900",
  "[&_td]:py-2 [&_td]:px-3 [&_td]:border-b [&_td]:border-gray-100 [&_td]:text-gray-800 [&_td]:align-top",
  "[&_blockquote]:border-l-4 [&_blockquote]:border-gray-300 [&_blockquote]:pl-4 [&_blockquote]:text-gray-600 [&_blockquote]:my-4 [&_blockquote]:italic",
  "[&_hr]:my-6 [&_hr]:border-gray-200",
]

/** Markdown renderer. Use `variant="document"` for full-page document view
 *  (white background, generous prose); default `compact` is tuned for cards
 *  and the chat stream via the typeset system. */
export function Markdown({ content, className, variant = "compact" }: MarkdownProps) {
  return (
    <div
      className={cn(
        variant === "document" ? documentStyles : "typeset typeset-chat",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
