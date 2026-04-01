import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import { mkdir } from 'node:fs/promises';
import net from 'node:net';
import process from 'node:process';

import { Endpoint, Headers } from '../constants.js';
import { logger } from './logger.js';
import { cookie_header, fetch_with_timeout, sleep } from './http.js';
import { read_cookie_file, type CookieMap, write_cookie_file } from './cookie-file.js';
import { resolveGeminiWebChromeProfileDir, resolveGeminiWebCookiePath } from './paths.js';

type CdpSendOptions = { sessionId?: string; timeoutMs?: number };

class CdpConnection {
  private ws: WebSocket;
  private nextId = 0;
  private pending = new Map<
    number,
    { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> | null }
  >();

  private constructor(ws: WebSocket) {
    this.ws = ws;
    this.ws.addEventListener('message', (event) => {
      try {
        const data = typeof event.data === 'string' ? event.data : new TextDecoder().decode(event.data as ArrayBuffer);
        const msg = JSON.parse(data) as { id?: number; result?: unknown; error?: { message?: string } };
        if (msg.id) {
          const p = this.pending.get(msg.id);
          if (p) {
            this.pending.delete(msg.id);
            if (p.timer) clearTimeout(p.timer);
            if (msg.error?.message) p.reject(new Error(msg.error.message));
            else p.resolve(msg.result);
          }
        }
      } catch {}
    });
    this.ws.addEventListener('close', () => {
      for (const [id, p] of this.pending.entries()) {
        this.pending.delete(id);
        if (p.timer) clearTimeout(p.timer);
        p.reject(new Error('CDP connection closed.'));
      }
    });
  }

  static async connect(url: string, timeoutMs: number): Promise<CdpConnection> {
    const ws = new WebSocket(url);
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('CDP connection timeout.')), timeoutMs);
      ws.addEventListener('open', () => {
        clearTimeout(t);
        resolve();
      });
      ws.addEventListener('error', () => {
        clearTimeout(t);
        reject(new Error('CDP connection failed.'));
      });
    });
    return new CdpConnection(ws);
  }

  async send<T = unknown>(method: string, params?: Record<string, unknown>, opts?: CdpSendOptions): Promise<T> {
    const id = ++this.nextId;
    const msg: Record<string, unknown> = { id, method };
    if (params) msg.params = params;
    if (opts?.sessionId) msg.sessionId = opts.sessionId;

    const timeoutMs = opts?.timeoutMs ?? 15_000;
    const out = await new Promise<unknown>((resolve, reject) => {
      const t =
        timeoutMs > 0
          ? setTimeout(() => {
              this.pending.delete(id);
              reject(new Error(`CDP timeout: ${method}`));
            }, timeoutMs)
          : null;
      this.pending.set(id, { resolve, reject, timer: t });
      this.ws.send(JSON.stringify(msg));
    });
    return out as T;
  }

  close(): void {
    try {
      this.ws.close();
    } catch {}
  }
}

async function get_free_port(): Promise<number> {
  const fixed = parseInt(process.env.GEMINI_WEB_DEBUG_PORT || '', 10);
  if (fixed > 0) return fixed;
  return await new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      if (!addr || typeof addr === 'string') {
        srv.close(() => reject(new Error('Unable to allocate a free TCP port.')));
        return;
      }
      const port = addr.port;
      srv.close((err) => (err ? reject(err) : resolve(port)));
    });
  });
}

function cleanup_existing_browser_processes(profileDir: string, verbose: boolean): void {
  try {
    if (process.platform === 'win32') {
      execFileSync(
        'powershell',
        [
          '-NoProfile',
          '-Command',
          "$p=$env:GEMINI_WEB_PROFILE_DIR; Get-CimInstance Win32_Process -Filter \"name = 'chrome.exe' or name = 'msedge.exe'\" | Where-Object { $_.CommandLine -like \"*$p*\" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
        ],
        {
          env: { ...process.env, GEMINI_WEB_PROFILE_DIR: profileDir },
          stdio: 'ignore',
          timeout: 10000,
        },
      );
      return;
    }
    if (process.platform === 'darwin' || process.platform === 'linux') {
      execFileSync('pkill', ['-f', profileDir], { stdio: 'ignore', timeout: 10000 });
    }
  } catch (e) {
    if (verbose) logger.debug(`Skipping profile browser cleanup: ${e instanceof Error ? e.message : String(e)}`);
  }
}

function detect_existing_debug_port(profileDir: string, verbose: boolean): number | null {
  try {
    if (process.platform === 'win32') {
      const raw = execFileSync(
        'powershell',
        [
          '-NoProfile',
          '-Command',
          "$p=$env:GEMINI_WEB_PROFILE_DIR; Get-CimInstance Win32_Process -Filter \"name = 'chrome.exe' or name = 'msedge.exe'\" | Where-Object { $_.CommandLine -like \"*$p*\" -and $_.CommandLine -match '--remote-debugging-port=(\\d+)' } | Select-Object -ExpandProperty CommandLine",
        ],
        {
          env: { ...process.env, GEMINI_WEB_PROFILE_DIR: profileDir },
          encoding: 'utf-8',
          timeout: 10000,
        },
      ).trim();
      if (!raw) return null;
      const match = raw.match(/--remote-debugging-port=(\d+)/);
      if (match) return parseInt(match[1]!, 10);
      return null;
    }
  } catch (e) {
    if (verbose) logger.debug(`Skipping existing debug browser detection: ${e instanceof Error ? e.message : String(e)}`);
  }
  return null;
}

function find_chrome_executable(): string | null {
  const override = process.env.GEMINI_WEB_CHROME_PATH?.trim();
  if (override && fs.existsSync(override)) return override;

  const candidates: string[] = [];
  switch (process.platform) {
    case 'darwin':
      candidates.push(
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
        '/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
      );
      break;
    case 'win32':
      candidates.push(
        'C:\\\\Program Files\\\\Google\\\\Chrome\\\\Application\\\\chrome.exe',
        'C:\\\\Program Files (x86)\\\\Google\\\\Chrome\\\\Application\\\\chrome.exe',
        'C:\\\\Program Files\\\\Microsoft\\\\Edge\\\\Application\\\\msedge.exe',
        'C:\\\\Program Files (x86)\\\\Microsoft\\\\Edge\\\\Application\\\\msedge.exe',
      );
      break;
    default:
      candidates.push(
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/snap/bin/chromium',
        '/usr/bin/microsoft-edge',
      );
      break;
  }

  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

async function wait_for_chrome_debug_port(port: number, timeoutMs: number): Promise<string> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch_with_timeout(`http://127.0.0.1:${port}/json/version`, { timeout_ms: 5_000 });
      if (!res.ok) throw new Error(`status=${res.status}`);
      const j = (await res.json()) as { webSocketDebuggerUrl?: string };
      if (j.webSocketDebuggerUrl) return j.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error('Chrome debug port not ready');
}

async function launch_chrome(profileDir: string, port: number): Promise<ChildProcess> {
  const chrome = find_chrome_executable();
  if (!chrome) throw new Error('Chrome executable not found.');

  const args = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-popup-blocking',
    'https://gemini.google.com/app',
  ];

  return spawn(chrome, args, { stdio: 'ignore' });
}

async function is_gemini_session_ready(cookies: CookieMap, verbose: boolean): Promise<boolean> {
  if (!cookies['__Secure-1PSID']) return false;

  try {
    const res = await fetch_with_timeout(Endpoint.INIT, {
      method: 'GET',
      headers: { ...Headers.GEMINI, Cookie: cookie_header(cookies) },
      redirect: 'follow',
      timeout_ms: 30_000,
    });

    if (!res.ok) {
      if (verbose) logger.debug(`Gemini init check failed: ${res.status} ${res.statusText}`);
      return false;
    }

    const text = await res.text();
    return /\"SNlM0e\":\"(.*?)\"/.test(text);
  } catch (e) {
    if (verbose) logger.debug(`Gemini init check error: ${e instanceof Error ? e.message : String(e)}`);
    return false;
  }
}

async function fetch_google_cookies_via_cdp(
  profileDir: string,
  timeoutMs: number,
  verbose: boolean,
): Promise<CookieMap> {
  await mkdir(profileDir, { recursive: true });
  let port = detect_existing_debug_port(profileDir, verbose);
  let chrome: ChildProcess | null = null;
  if (!port) {
    cleanup_existing_browser_processes(profileDir, verbose);
    port = await get_free_port();
    chrome = await launch_chrome(profileDir, port);
  }

  let cdp: CdpConnection | null = null;
  try {
    let wsUrl: string;
    try {
      wsUrl = await wait_for_chrome_debug_port(port, 60_000);
    } catch (e) {
      if (!chrome && port) {
        cleanup_existing_browser_processes(profileDir, verbose);
        port = await get_free_port();
        chrome = await launch_chrome(profileDir, port);
        wsUrl = await wait_for_chrome_debug_port(port, 60_000);
      } else {
        throw e;
      }
    }
    cdp = await CdpConnection.connect(wsUrl, 15_000);

    const { targetId } = await cdp.send<{ targetId: string }>('Target.createTarget', {
      url: 'https://gemini.google.com/app',
      newWindow: true,
    });
    const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId, flatten: true });
    await cdp.send('Network.enable', {}, { sessionId });

    if (verbose) {
      logger.info('Chrome opened. If needed, complete Google login in the window. Waiting for a valid Gemini session...');
    }

    const start = Date.now();
    let last: CookieMap = {};

    while (Date.now() - start < timeoutMs) {
      try {
        const { cookies } = await cdp.send<{ cookies: Array<{ name: string; value: string }> }>(
          'Network.getCookies',
          { urls: ['https://gemini.google.com/', 'https://accounts.google.com/', 'https://www.google.com/'] },
          { sessionId, timeoutMs: 20_000 },
        );

        const m: CookieMap = {};
        for (const c of cookies) {
          if (c?.name && typeof c.value === 'string') m[c.name] = c.value;
        }

        last = m;
        if (await is_gemini_session_ready(m, verbose)) {
          return m;
        }
      } catch (e) {
        if (verbose) logger.debug(`CDP getCookies retry: ${e instanceof Error ? e.message : String(e)}`);
      }

      await sleep(1000);
    }

    throw new Error(`Timed out waiting for a valid Gemini session. Last keys: ${Object.keys(last).join(', ')}`);
  } finally {
    if (cdp) {
      try {
        await cdp.send('Browser.close', {}, { timeoutMs: 5_000 });
      } catch {}
      cdp.close();
    }

    if (chrome) {
      try {
        chrome.kill('SIGTERM');
      } catch {}
      setTimeout(() => {
        if (chrome && !chrome.killed) {
          try {
            chrome.kill('SIGKILL');
          } catch {}
        }
      }, 2_000).unref?.();
    }
  }
}

function has_required_session_cookies(cookies: CookieMap | null | undefined): boolean {
  if (!cookies) return false;
  return !!(cookies['__Secure-1PSID'] && cookies['__Secure-1PSIDTS']);
}

async function write_cached_sidts(cookies: CookieMap): Promise<void> {
  const sid = cookies['__Secure-1PSID'];
  const sidts = cookies['__Secure-1PSIDTS'];
  if (!sid || !sidts) return;
  const dir = path.dirname(resolveGeminiWebCookiePath());
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, `.cached_1psidts_${sid}.txt`), sidts, 'utf8');
}

export async function load_browser_cookies(
  domain_name: string = '',
  verbose: boolean = true,
  force_refresh: boolean = false,
): Promise<Record<string, CookieMap>> {
  const force = force_refresh || !!(process.env.GEMINI_WEB_LOGIN?.trim() || process.env.GEMINI_WEB_FORCE_LOGIN?.trim());
  if (!force) {
    const cached = await read_cookie_file();
    if (has_required_session_cookies(cached)) return { chrome: cached };
  }

  const profileDir = process.env.GEMINI_WEB_CHROME_PROFILE_DIR?.trim() || resolveGeminiWebChromeProfileDir();
  const cookies = await fetch_google_cookies_via_cdp(profileDir, 120_000, verbose);

  const filtered: CookieMap = {};
  for (const [k, v] of Object.entries(cookies)) {
    if (typeof v === 'string' && v.length > 0) filtered[k] = v;
  }

  await write_cached_sidts(filtered).catch(() => {});
  await write_cookie_file(filtered, resolveGeminiWebCookiePath(), 'cdp');
  void domain_name;
  return { chrome: filtered };
}

export const loadBrowserCookies = load_browser_cookies;
