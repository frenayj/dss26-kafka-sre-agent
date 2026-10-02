import { useMemo, useState } from "react"
import { Chip } from "@/components/shared/chip"
import { CountPill } from "@/components/shared/count-pill"
import { EmptyState } from "@/components/shared/empty-state"
import { StatStrip, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { parseArrayToolResult } from "./parse"
import type { SqlResultRow } from "./types"

interface Props {
  result: string
}

const MAX_VISIBLE_ROWS = 50
const MAX_CELL_LENGTH = 120
const OUTLIER_THRESHOLD = 2 // standard deviations
const INTERNAL_FIELDS = new Set(["_partition", "_offset", "_key", "_headers"])
const NO_ROWS: Record<string, unknown>[] = []

// ---- numeric helpers ------------------------------------------------------

function isNumeric(v: unknown): boolean {
  if (typeof v === "number") return true
  if (typeof v === "string" && v !== "") return !isNaN(Number(v))
  return false
}

function toNumber(v: unknown): number | null {
  if (typeof v === "number") return v
  if (typeof v === "string" && v !== "") {
    const n = Number(v)
    return isNaN(n) ? null : n
  }
  return null
}

interface ColumnStats {
  min: number
  max: number
  mean: number
  stdDev: number
  count: number
}

function computeStats(values: (number | null)[]): ColumnStats | null {
  const nums = values.filter((v): v is number => v !== null)
  if (nums.length < 2) return null
  const sum = nums.reduce((a, b) => a + b, 0)
  const mean = sum / nums.length
  const variance = nums.reduce((a, b) => a + (b - mean) ** 2, 0) / nums.length
  const stdDev = Math.sqrt(variance)
  return { min: Math.min(...nums), max: Math.max(...nums), mean, stdDev, count: nums.length }
}

function isOutlier(value: number, stats: ColumnStats): boolean {
  if (stats.stdDev === 0) return false
  return Math.abs(value - stats.mean) > OUTLIER_THRESHOLD * stats.stdDev
}

function formatCompact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  if (Number.isInteger(n)) return String(n)
  return n.toFixed(2)
}

function formatCell(value: unknown): { display: string; isNull: boolean; numeric: boolean } {
  if (value === null || value === undefined) {
    return { display: "NULL", isNull: true, numeric: false }
  }
  const numeric = isNumeric(value)
  const str = typeof value === "string" ? value : JSON.stringify(value)
  const display =
    str.length > MAX_CELL_LENGTH ? str.slice(0, MAX_CELL_LENGTH) + "…" : str
  return { display, isNull: false, numeric }
}

function formatTimestamp(ts: number): string {
  try {
    return new Date(ts).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })
  } catch {
    return String(ts)
  }
}

function isMcpRow(row: unknown): row is SqlResultRow {
  return (
    typeof row === "object" &&
    row !== null &&
    "value" in row &&
    typeof (row as SqlResultRow).value === "object"
  )
}

// ---- component ------------------------------------------------------------

const HEAD_CLASS =
  "h-auto border-b border-border px-3 py-1.5 text-[10px] font-medium tracking-wider text-muted-foreground uppercase"

export function SqlQuery({ result }: Props) {
  // Parse once per result string so the derived memos below stay stable.
  const parsed = useMemo(
    () => parseArrayToolResult<SqlResultRow | Record<string, unknown>>(result),
    [result],
  )
  const rawRows = parsed.ok ? parsed.data : NO_ROWS
  const mcpShape = rawRows.length > 0 && isMcpRow(rawRows[0])

  // All hooks must run before any conditional return (rules of hooks).
  const { dataRows, metadataRows } = useMemo(() => {
    if (mcpShape) {
      const mcpRows = rawRows as SqlResultRow[]
      return {
        dataRows: mcpRows.map((r) => {
          const v: Record<string, unknown> = {}
          for (const [k, val] of Object.entries(r.value)) {
            if (!INTERNAL_FIELDS.has(k)) v[k] = val
          }
          return v
        }),
        metadataRows: mcpRows.map((r) => r.metadata ?? {}),
      }
    }
    return {
      dataRows: rawRows as Record<string, unknown>[],
      metadataRows: [] as Record<string, unknown>[],
    }
  }, [rawRows, mcpShape])

  const [showMetadata, setShowMetadata] = useState(false)
  const [sortCol, setSortCol] = useState<string | null>(null)
  const [sortAsc, setSortAsc] = useState(true)

  const columns = useMemo(() => {
    if (dataRows.length === 0) return []
    const all = new Set<string>()
    for (const row of dataRows) for (const k of Object.keys(row)) all.add(k)
    return Array.from(all).filter((k) =>
      dataRows.some((r) => r[k] !== null && r[k] !== undefined),
    )
  }, [dataRows])

  const { numericCols, colStats } = useMemo(() => {
    const numericCols = new Set<string>()
    const colStats: Record<string, ColumnStats> = {}
    for (const col of columns) {
      const values = dataRows.map((r) => toNumber(r[col]))
      const numCount = values.filter((v) => v !== null).length
      if (numCount > dataRows.length * 0.5) {
        numericCols.add(col)
        const stats = computeStats(values)
        if (stats) colStats[col] = stats
      }
    }
    return { numericCols, colStats }
  }, [columns, dataRows])

  const outlierCount = useMemo(() => {
    let count = 0
    for (const col of Object.keys(colStats)) {
      for (const row of dataRows) {
        const n = toNumber(row[col])
        if (n !== null && isOutlier(n, colStats[col])) count++
      }
    }
    return count
  }, [dataRows, colStats])

  const sortedIndices = useMemo(() => {
    const indices = dataRows.map((_, i) => i)
    if (!sortCol) return indices
    return [...indices].sort((a, b) => {
      const av = dataRows[a][sortCol]
      const bv = dataRows[b][sortCol]
      const an = toNumber(av)
      const bn = toNumber(bv)
      if (an !== null && bn !== null) return sortAsc ? an - bn : bn - an
      const as = String(av ?? "")
      const bs = String(bv ?? "")
      return sortAsc ? as.localeCompare(bs) : bs.localeCompare(as)
    })
  }, [dataRows, sortCol, sortAsc])

  const topics = useMemo(() => {
    const set = new Set<string>()
    metadataRows.forEach((m) => {
      if (m.topic) set.add(String(m.topic))
    })
    return Array.from(set)
  }, [metadataRows])

  // Now safe to early-return.
  if (!parsed.ok) return null

  if (rawRows.length === 0) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold">SQL result</span>
          <CountPill>0 rows</CountPill>
        </div>
        <EmptyState title="No results returned." />
      </div>
    )
  }

  const visibleIndices = sortedIndices.slice(0, MAX_VISIBLE_ROWS)
  const remainingRows = sortedIndices.length - MAX_VISIBLE_ROWS

  function handleSort(col: string) {
    if (sortCol === col) setSortAsc((v) => !v)
    else {
      setSortCol(col)
      setSortAsc(true)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold">SQL result</span>
        <CountPill>
          {dataRows.length} row{dataRows.length !== 1 ? "s" : ""}
        </CountPill>
        <CountPill>
          {columns.length} col{columns.length !== 1 ? "s" : ""}
        </CountPill>
        {Object.keys(colStats).length > 0 && (
          <StatusBadge tone="info">{Object.keys(colStats).length} numeric</StatusBadge>
        )}
        {outlierCount > 0 && (
          <StatusBadge tone="warning">
            {outlierCount} outlier{outlierCount !== 1 ? "s" : ""}
          </StatusBadge>
        )}
        {mcpShape && metadataRows.length > 0 && (
          <Button
            variant="ghost"
            size="xs"
            onClick={() => setShowMetadata((v) => !v)}
            className="ml-auto font-normal text-muted-foreground"
          >
            {showMetadata ? "Hide metadata" : "Show metadata"}
          </Button>
        )}
      </div>

      {topics.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {topics.map((t) => (
            <Chip key={t}>{t}</Chip>
          ))}
        </div>
      )}

      {Object.keys(colStats).length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
            Column statistics
          </span>
          <div
            className="grid gap-1.5"
            style={{
              gridTemplateColumns: `repeat(${Math.min(Object.keys(colStats).length, 3)}, 1fr)`,
            }}
          >
            {Object.entries(colStats).map(([col, stats]) => {
              const range = stats.max - stats.min
              const meanPct = range > 0 ? ((stats.mean - stats.min) / range) * 100 : 50
              return (
                <div
                  key={col}
                  className="overflow-hidden rounded-md border border-border bg-card"
                >
                  <div className="truncate px-2 pt-1.5 font-mono text-xs text-info">
                    {col}
                  </div>
                  <StatStrip>
                    <StatTile label="min" value={formatCompact(stats.min)} />
                    <StatTile label="max" value={formatCompact(stats.max)} />
                    <StatTile label="avg" value={formatCompact(stats.mean)} />
                    <StatTile label="σ" value={formatCompact(stats.stdDev)} />
                  </StatStrip>
                  {/* Mean-marker mini-bar: Meter can't express a positioned
                      marker dot, so this stays custom (info-toned). */}
                  <div className="relative mx-2 mb-2 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="absolute inset-y-0 right-0 left-0 rounded-full bg-info/40" />
                    <div
                      className="absolute top-0 size-1.5 rounded-full bg-info"
                      style={{
                        left: `${Math.max(1, Math.min(99, meanPct))}%`,
                        transform: "translateX(-50%)",
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Single scroll container (vertical + horizontal): the inner shadcn
          table wrapper is forced to overflow-visible so the sticky header
          sticks to this scrollport, as before. */}
      <div className="mac-scrollbar max-h-[28rem] overflow-x-auto rounded-md border border-border [&_[data-slot=table-container]]:overflow-visible">
        <Table className="border-collapse font-mono text-xs">
          <TableHeader className="sticky top-0 z-10 bg-card">
            <TableRow className="hover:bg-transparent">
              <TableHead className={cn(HEAD_CLASS, "w-8 px-2 text-right")}>#</TableHead>
              {columns.map((col) => {
                const isNum = numericCols.has(col)
                const isSorted = sortCol === col
                return (
                  <TableHead
                    key={col}
                    onClick={() => handleSort(col)}
                    className={cn(
                      HEAD_CLASS,
                      "cursor-pointer transition-colors select-none hover:text-foreground",
                      isSorted && "text-info",
                      isNum ? "text-right" : "text-left",
                    )}
                  >
                    {col}
                    {isSorted && <span className="ml-1">{sortAsc ? "↑" : "↓"}</span>}
                  </TableHead>
                )
              })}
              {showMetadata && (
                <>
                  <TableHead className={cn(HEAD_CLASS, "px-2 text-right")}>
                    partition
                  </TableHead>
                  <TableHead className={cn(HEAD_CLASS, "px-2 text-right")}>
                    offset
                  </TableHead>
                  <TableHead className={cn(HEAD_CLASS, "px-2 text-left")}>
                    timestamp
                  </TableHead>
                </>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleIndices.map((rowIdx, displayIdx) => {
              const row = dataRows[rowIdx]
              const meta = metadataRows[rowIdx]
              return (
                <TableRow
                  key={rowIdx}
                  className={cn(displayIdx % 2 === 1 && "bg-card/40")}
                >
                  <TableCell className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
                    {rowIdx + 1}
                  </TableCell>
                  {columns.map((col) => {
                    const { display, isNull, numeric } = formatCell(row[col])
                    const n = toNumber(row[col])
                    const stats = colStats[col]
                    const outlier = n !== null && stats && isOutlier(n, stats)
                    const raw = row[col]
                    const fullStr = typeof raw === "string" ? raw : JSON.stringify(raw)
                    return (
                      <TableCell
                        key={col}
                        className={cn(
                          "max-w-[300px] truncate px-3 py-1.5",
                          isNull
                            ? "text-muted-foreground italic"
                            : outlier
                              ? "bg-warning/5 font-semibold text-warning"
                              : "text-foreground",
                          (numeric || numericCols.has(col)) && "text-right tabular-nums",
                        )}
                        title={
                          outlier && stats
                            ? `${fullStr} (μ=${formatCompact(stats.mean)}, σ=${formatCompact(stats.stdDev)})`
                            : fullStr ?? ""
                        }
                      >
                        {display}
                      </TableCell>
                    )
                  })}
                  {showMetadata && meta && (
                    <>
                      <TableCell className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
                        {meta.partition != null ? String(meta.partition) : "-"}
                      </TableCell>
                      <TableCell className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
                        {meta.offset != null ? String(meta.offset) : "-"}
                      </TableCell>
                      <TableCell className="px-2 py-1.5 text-left text-muted-foreground">
                        {typeof meta.timestamp === "number"
                          ? formatTimestamp(meta.timestamp)
                          : "-"}
                      </TableCell>
                    </>
                  )}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        {remainingRows > 0 && (
          <div className="border-t border-border bg-card px-3 py-1.5 text-xs text-muted-foreground italic">
            + {remainingRows} more row{remainingRows !== 1 ? "s" : ""} not shown
          </div>
        )}
      </div>
    </div>
  )
}
