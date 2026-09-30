/**
 * otk:// serves the UI and preview images without any local web server.
 *
 *   otk://app/<path>     built renderer files (production)
 *   otk://file/<token>   a file the main process registered (previews only);
 *                        unregistered paths are never served.
 */

import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize, relative } from 'node:path'
import { protocol } from 'electron'

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.map': 'application/json'
}

export const CSP = [
  "default-src 'self' otk:",
  "script-src 'self' otk:",
  "style-src 'self' otk: 'unsafe-inline'",
  "img-src 'self' otk: data: blob:",
  "font-src 'self' otk: data:",
  "connect-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'"
].join('; ')

const files = new Map<string, string>()
const byPath = new Map<string, string>()

export function registerSchemes(): void {
  protocol.registerSchemesAsPrivileged([
    { scheme: 'otk', privileges: { standard: true, secure: true, supportFetchAPI: false, stream: true, codeCache: true } }
  ])
}

/** Make a file available to the renderer; returns its otk:// URL. */
export function fileUrl(path: string): string {
  let token = byPath.get(path)
  if (!token) {
    token = randomUUID()
    files.set(token, path)
    byPath.set(path, token)
  }
  return `otk://file/${token}${extname(path).toLowerCase()}`
}

export function forgetFile(path: string): void {
  const token = byPath.get(path)
  if (token) {
    files.delete(token)
    byPath.delete(path)
  }
}

async function serve(path: string, extraHeaders: Record<string, string> = {}): Promise<Response> {
  try {
    const body = await readFile(path)
    const type = MIME[extname(path).toLowerCase()] ?? 'application/octet-stream'
    return new Response(body, { headers: { 'content-type': type, 'cache-control': 'no-store', ...extraHeaders } })
  } catch {
    return new Response('Not found', { status: 404 })
  }
}

export function handleProtocol(rendererDir: string): void {
  protocol.handle('otk', async (request) => {
    const url = new URL(request.url)
    if (url.host === 'file') {
      const token = url.pathname.slice(1).replace(/\.[a-z0-9]+$/i, '')
      const path = files.get(token)
      return path ? serve(path) : new Response('Not found', { status: 404 })
    }
    if (url.host === 'app') {
      const rel = decodeURIComponent(url.pathname).replace(/^\/+/, '') || 'index.html'
      const full = normalize(join(rendererDir, rel))
      if (relative(rendererDir, full).startsWith('..')) return new Response('Forbidden', { status: 403 })
      return serve(full, full.endsWith('.html') ? { 'content-security-policy': CSP } : {})
    }
    return new Response('Not found', { status: 404 })
  })
}
