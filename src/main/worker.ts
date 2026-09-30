/**
 * Python worker processes speaking JSON-RPC over stdio (no sockets).
 *
 * Two workers: one for interactive requests (probe, preview) and one for
 * batch jobs, so a long batch never blocks the preview. A worker that dies is
 * restarted on the next request; its pending calls fail with a clear error.
 */

import { type ChildProcessWithoutNullStreams, spawn } from 'node:child_process'
import { EventEmitter } from 'node:events'
import type { EventLog } from './log'
import { recordViolation } from './offline-guard'

export class WorkerError extends Error {
  constructor(message: string, public code: string, public data?: unknown) {
    super(message)
  }
}

interface Pending {
  resolve: (v: unknown) => void
  reject: (e: Error) => void
  method: string
  timer?: NodeJS.Timeout
}

export interface WorkerOptions {
  name: string
  python: string
  workerDir: string
  resourcesDir: string
  log: EventLog
}

export class WorkerProcess extends EventEmitter {
  private proc: ChildProcessWithoutNullStreams | null = null
  private pending = new Map<number, Pending>()
  private nextId = 1
  private buffer = ''
  private stderrTail: string[] = []
  private starting: Promise<void> | null = null

  constructor(private opts: WorkerOptions) {
    super()
  }

  get running(): boolean {
    return this.proc !== null && this.proc.exitCode === null
  }

  private start(): Promise<void> {
    if (this.running) return Promise.resolve()
    if (this.starting) return this.starting
    const { python, workerDir, resourcesDir, log, name } = this.opts
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      PYTHONPATH: workerDir,
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONDONTWRITEBYTECODE: '1',
      OTK_RESOURCES: resourcesDir,
      OTK_NETGUARD: '1',
      // Any library that honours proxies fails fast instead of reaching out.
      HTTP_PROXY: 'http://127.0.0.1:9',
      HTTPS_PROXY: 'http://127.0.0.1:9',
      ALL_PROXY: 'http://127.0.0.1:9',
      NO_PROXY: '',
      HF_HUB_OFFLINE: '1',
      TRANSFORMERS_OFFLINE: '1'
    }
    delete env.http_proxy
    delete env.https_proxy
    delete env.no_proxy
    this.starting = new Promise<void>((resolve, reject) => {
      let proc: ChildProcessWithoutNullStreams
      try {
        proc = spawn(python, ['-X', 'utf8', '-u', '-m', 'otk_worker'], { cwd: workerDir, env, windowsHide: true })
      } catch (e) {
        this.starting = null
        reject(new WorkerError(`Could not start the Python worker (${python}): ${(e as Error).message}`, 'worker_start'))
        return
      }
      this.proc = proc
      proc.stdout.setEncoding('utf-8')
      proc.stderr.setEncoding('utf-8')
      proc.stdout.on('data', (chunk: string) => this.onStdout(chunk))
      proc.stderr.on('data', (chunk: string) => this.onStderr(chunk))
      proc.once('error', (err) => {
        log.error('worker', `${name} worker failed to start: ${err.message}`, { python })
        this.failAll(new WorkerError(`The Python worker could not start (${python}). See Settings → Diagnostics.`, 'worker_start'))
        this.proc = null
        this.starting = null
        reject(err)
      })
      proc.once('spawn', () => {
        log.info('worker', `${name} worker started (pid ${proc.pid})`)
        this.starting = null
        resolve()
      })
      proc.once('exit', (code, signal) => {
        const tail = this.stderrTail.slice(-8).join('\n')
        if (code !== 0 && signal !== 'SIGTERM') log.warn('worker', `${name} worker exited (code ${code}, signal ${signal})`, { tail })
        this.failAll(new WorkerError(`The ${name} worker stopped unexpectedly. It will restart on the next request.`, 'worker_exit', { tail }))
        this.proc = null
        this.emit('exit')
      })
    })
    return this.starting
  }

  private onStdout(chunk: string): void {
    this.buffer += chunk
    let nl: number
    while ((nl = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, nl).trim()
      this.buffer = this.buffer.slice(nl + 1)
      if (!line) continue
      let msg: { id?: number; result?: unknown; error?: { message: string; code: number; data?: { code?: string } }; method?: string; params?: unknown }
      try {
        msg = JSON.parse(line)
      } catch {
        this.opts.log.warn('worker', `Unreadable worker output: ${line.slice(0, 200)}`)
        continue
      }
      if (msg.id !== undefined && msg.id !== null) {
        const p = this.pending.get(msg.id)
        if (!p) continue
        this.pending.delete(msg.id)
        if (p.timer) clearTimeout(p.timer)
        if (msg.error) p.reject(new WorkerError(msg.error.message, msg.error.data?.code ?? String(msg.error.code), msg.error.data))
        else p.resolve(msg.result)
      } else if (msg.method) {
        this.emit('notification', msg.method, msg.params)
      }
    }
  }

  private onStderr(chunk: string): void {
    for (const line of chunk.split(/\r?\n/)) {
      if (!line.trim()) continue
      if (line.startsWith('OFFLINE_VIOLATION ')) {
        recordViolation('python', line.slice('OFFLINE_VIOLATION '.length))
        continue
      }
      if (line.startsWith('OFFLINE_GUARD_FAILED')) this.opts.log.error('offline-guard', `Python network guard failed to load: ${line}`)
      this.stderrTail.push(line)
      if (this.stderrTail.length > 50) this.stderrTail.shift()
    }
  }

  private failAll(err: Error): void {
    for (const [, p] of this.pending) {
      if (p.timer) clearTimeout(p.timer)
      p.reject(err)
    }
    this.pending.clear()
  }

  async request<T>(method: string, params: Record<string, unknown> = {}, timeoutMs = 0): Promise<T> {
    await this.start()
    const id = this.nextId++
    return new Promise<T>((resolve, reject) => {
      const p: Pending = { resolve: resolve as (v: unknown) => void, reject, method }
      if (timeoutMs > 0) {
        p.timer = setTimeout(() => {
          this.pending.delete(id)
          reject(new WorkerError(`The worker did not answer ${method} in time.`, 'timeout'))
        }, timeoutMs)
      }
      this.pending.set(id, p)
      this.proc!.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n')
    })
  }

  kill(): void {
    if (this.proc && this.proc.exitCode === null) {
      this.proc.kill()
    }
  }

  async stop(): Promise<void> {
    if (!this.proc) return
    const proc = this.proc
    proc.stdin.end()
    await new Promise<void>((resolve) => {
      const t = setTimeout(() => {
        proc.kill()
        resolve()
      }, 3000)
      proc.once('exit', () => {
        clearTimeout(t)
        resolve()
      })
    })
  }
}

export class WorkerPool {
  readonly interactive: WorkerProcess
  readonly jobs: WorkerProcess
  private activeJobs = new Set<string>()

  constructor(base: Omit<WorkerOptions, 'name'>) {
    this.interactive = new WorkerProcess({ ...base, name: 'interactive' })
    this.jobs = new WorkerProcess({ ...base, name: 'jobs' })
  }

  async runJob<T>(jobId: string, method: string, params: Record<string, unknown>): Promise<T> {
    this.activeJobs.add(jobId)
    try {
      return await this.jobs.request<T>(method, { ...params, jobId })
    } finally {
      this.activeJobs.delete(jobId)
    }
  }

  /** Ask politely; if the job is still running after `graceMs`, restart the jobs worker. */
  async cancel(jobId: string, graceMs = 10_000): Promise<void> {
    const worker = this.activeJobs.has(jobId) ? this.jobs : this.interactive
    try {
      await worker.request('job.cancel', { jobId }, 5000)
    } catch {
      /* worker gone already */
    }
    if (worker === this.jobs && this.activeJobs.has(jobId)) {
      setTimeout(() => {
        if (this.activeJobs.has(jobId)) worker.kill()
      }, graceMs)
    }
  }

  async stop(): Promise<void> {
    await Promise.all([this.interactive.stop(), this.jobs.stop()])
  }
}
