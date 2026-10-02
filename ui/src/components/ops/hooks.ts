import { useCallback, useEffect, useRef, useState } from "react"
import {
  fetchOpsActions,
  fetchOpsJob,
  fetchOpsStatus,
  type OpsAction,
  type OpsJob,
  type OpsStatus,
} from "@/lib/ops"

const STATUS_POLL_MS = 2_000
const ACTIONS_RETRY_MS = 3_000
const JOB_POLL_RUNNING_MS = 1_000
// Slower while idle, so a job started from another tab still shows up.
const JOB_POLL_IDLE_MS = 3_000
/** Lag samples kept for the sparkline (~5 minutes at the server's 5s cadence). */
export const LAG_SAMPLES = 60
/** Client-side cap on the output buffer, matching the server's. */
const MAX_LINES = 5_000

/**
 * Run `tick` now, then again `delay()` ms after each run settles, so a slow
 * server never stacks requests. `delay()` returning null stops the loop.
 * `wake()` runs the next tick right away (or right after the one in flight).
 */
function startPolling(tick: () => Promise<void>, delay: () => number | null) {
  let timer: number | undefined
  let stopped = false
  let busy = false
  let again = false

  const run = async () => {
    if (stopped) return
    if (busy) {
      again = true
      return
    }
    window.clearTimeout(timer)
    busy = true
    try {
      await tick()
    } catch {
      // Ticks report their own errors; keep polling regardless.
    } finally {
      busy = false
    }
    if (stopped) return
    if (again) {
      again = false
      void run()
      return
    }
    const ms = delay()
    if (ms !== null) timer = window.setTimeout(run, ms)
  }

  void run()
  return {
    stop: () => {
      stopped = true
      window.clearTimeout(timer)
    },
    wake: () => void run(),
  }
}

/** Epoch ms, re-rendering every `intervalMs` (for "Ns ago" and timers). */
export function useNow(intervalMs = 1_000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

/** GET /status every 2s, plus the consumer-lag history for the sparkline.
 *  `connected` is null until the first request settles. */
export function useOpsStatus() {
  const [status, setStatus] = useState<OpsStatus | null>(null)
  const [connected, setConnected] = useState<boolean | null>(null)
  const [lagHistory, setLagHistory] = useState<number[]>([])

  useEffect(() => {
    let cancelled = false
    // The server re-checks the consumer every 5s; sample each check once.
    let lastLagCheck = 0
    const poller = startPolling(
      async () => {
        try {
          const res = await fetchOpsStatus()
          if (cancelled) return
          setStatus(res)
          setConnected(true)
          const consumer = res.consumer
          if (consumer && consumer.error === null && consumer.checked_at !== lastLagCheck) {
            lastLagCheck = consumer.checked_at
            setLagHistory((prev) => [...prev, consumer.lag].slice(-LAG_SAMPLES))
          }
        } catch {
          if (!cancelled) setConnected(false)
        }
      },
      () => STATUS_POLL_MS,
    )
    return () => {
      cancelled = true
      poller.stop()
    }
  }, [])

  return { status, connected, lagHistory }
}

/** GET /actions, retried until the server answers once. */
export function useOpsActions() {
  const [actions, setActions] = useState<OpsAction[] | null>(null)

  useEffect(() => {
    let cancelled = false
    let loaded = false
    const poller = startPolling(
      async () => {
        const res = await fetchOpsActions()
        if (cancelled) return
        loaded = true
        setActions(res)
      },
      () => (loaded ? null : ACTIONS_RETRY_MS),
    )
    return () => {
      cancelled = true
      poller.stop()
    }
  }, [])

  return actions
}

/**
 * The current or last job and its output, appended incrementally via
 * GET /job?after=N: every 1s while it runs, every 3s otherwise. `refresh()`
 * polls immediately (call it after starting or stopping a job).
 */
export function useOpsJob() {
  const [job, setJob] = useState<OpsJob | null>(null)
  const [lines, setLines] = useState<string[]>([])
  const wakeRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    let cancelled = false
    // Ids restart at 1 with the server, so a job is its id plus start time.
    let jobKey: string | null = null
    let next = 0
    let running = false

    const poller = startPolling(
      async () => {
        let res = await fetchOpsJob(next)
        if (cancelled) return
        if (res.job === null) {
          // No job yet, or the server restarted and forgot it.
          if (jobKey !== null) {
            jobKey = null
            next = 0
            running = false
            setJob(null)
            setLines([])
          }
          return
        }
        if (`${res.job.id}:${res.job.started_at}` !== jobKey) {
          // A new job: restart its output from the top.
          if (next !== 0) res = await fetchOpsJob(0)
          if (cancelled || res.job === null) return
          jobKey = `${res.job.id}:${res.job.started_at}`
          next = res.next
          running = res.job.status === "running"
          setJob(res.job)
          setLines(res.lines.slice(-MAX_LINES))
          return
        }
        next = res.next
        running = res.job.status === "running"
        setJob(res.job)
        const added = res.lines
        if (added.length > 0) {
          setLines((prev) => [...prev, ...added].slice(-MAX_LINES))
        }
      },
      () => (running ? JOB_POLL_RUNNING_MS : JOB_POLL_IDLE_MS),
    )
    wakeRef.current = poller.wake
    return () => {
      cancelled = true
      wakeRef.current = null
      poller.stop()
    }
  }, [])

  const refresh = useCallback(() => wakeRef.current?.(), [])

  return { job, lines, refresh }
}
