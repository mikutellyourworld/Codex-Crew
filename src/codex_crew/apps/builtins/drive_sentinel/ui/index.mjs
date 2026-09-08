/**
 * Drive Sentinel — Codex Crew app panel.
 *
 * One section per engine capability, each labelled, because the point of this
 * panel is that nothing Drive Sentinel can do is hidden behind an agent prompt.
 *
 * Everything talks to /apps/drive-sentinel/api/*, which Codex Crew proxies to
 * the bundled local backend. The page never reaches loopback itself.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from 'react/jsx-runtime'
import {
  ageLabel,
  providerAllowsPin,
  rootsMatch,
  sweepItemBytes,
  sweepItems,
  sweepTotalBytes,
  timestampMillis,
  volumeOptionLabel,
} from './model.mjs'

const API = '/apps/drive-sentinel/api'
const GB = 1024 ** 3

// ── tokens ────────────────────────────────────────────────────────────────
// Theme vars with fallbacks so an older host without a token still renders.
const T = {
  bg: 'color-mix(in srgb, var(--bg, #07110e) 88%, #031b11)',
  card: 'color-mix(in srgb, var(--card, #0a1712) 90%, #052014)',
  text: 'var(--text, #d6f8df)',
  muted: 'var(--muted, #779383)',
  border: 'color-mix(in srgb, var(--border, #284236) 72%, #1f8a4c)',
  accent: '#35d06f',
  ok: '#35d06f',
  warn: '#f6b94a',
  danger: 'var(--danger, #b91c1c)',
}
const RISK = {
  safe: { fg: T.ok, bg: 'rgba(53,208,111,.12)', help: 'Regenerated automatically. Swept unattended.' },
  review: { fg: T.warn, bg: 'rgba(246,185,74,.12)', help: 'Costs a rebuild or a large re-download. Explicit instruction only.' },
  danger: { fg: T.danger, bg: 'rgba(185,28,28,.15)', help: 'Report only — the engine refuses to delete these.' },
}

// ── formatting ────────────────────────────────────────────────────────────
function bytes(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = Number(n)
  let i = 0
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i += 1 }
  return `${v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)} ${u[i]}`
}
function ago(iso) {
  return ageLabel(iso)
}
function clock(sec) {
  const s = Math.max(0, Math.floor(sec))
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}

// ── primitives ────────────────────────────────────────────────────────────
function Btn({ children, onClick, disabled, kind = 'ghost', title }) {
  const base = {
    borderRadius: '2px', fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace',
    fontSize: '10px', fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', padding: '6px 12px',
    cursor: disabled ? 'default' : 'pointer', whiteSpace: 'nowrap', opacity: disabled ? 0.55 : 1,
  }
  const skin = kind === 'primary'
    ? { background: T.accent, color: '#04130a', border: `1px solid ${T.accent}` }
    : kind === 'danger'
      ? { background: 'transparent', color: T.danger, border: `1px solid ${T.danger}` }
      : { background: 'transparent', color: T.accent, border: `1px solid ${T.accent}` }
  return _jsx('button', { onClick, disabled, title, style: { ...base, ...skin }, children })
}

function Badge({ children, fg = T.accent, bg = 'rgba(53,208,111,.12)', title }) {
  return _jsx('span', {
    title,
    style: {
      background: bg, color: fg, padding: '2px 6px', borderRadius: '2px',
      border: `1px solid color-mix(in srgb, ${fg} 45%, transparent)`,
      fontSize: '9px', fontWeight: 700, letterSpacing: '.09em', whiteSpace: 'nowrap',
    },
    children,
  })
}

function Card({ title, hint, right, children }) {
  return _jsxs('section', {
    style: {
      background: T.card, border: `1px solid ${T.border}`, borderLeft: `3px solid ${T.accent}`, borderRadius: '2px',
      padding: '14px', marginBottom: '10px',
    },
    children: [
      _jsxs('div', {
        style: { display: 'flex', alignItems: 'baseline', gap: '10px', marginBottom: '8px' },
        children: [
          _jsx('h3', { style: { margin: 0, fontSize: '12px', fontWeight: 700, color: T.accent, letterSpacing: '.04em' }, children: title }),
          hint ? _jsx('span', { style: { fontSize: '11px', color: T.muted }, children: hint }) : null,
          _jsx('span', { style: { marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }, children: right || null }),
        ],
      }),
      children,
    ],
  })
}

function Table({ head, rows, empty }) {
  if (!rows.length) return _jsx('div', { style: { fontSize: '11px', color: T.muted, padding: '6px 0' }, children: empty })
  return _jsxs('div', { style: { fontSize: '12px' }, children: [
    _jsx('div', {
      style: {
        display: 'flex', gap: '8px', padding: '4px 0', color: T.muted,
        fontSize: '10px', textTransform: 'uppercase', letterSpacing: '.04em',
        borderBottom: `1px solid ${T.border}`,
      },
      children: head.map((h, i) => _jsx('span', { style: h.style, children: h.label }, `h${i}`)),
    }),
    ...rows,
  ] })
}

function Row({ children }) {
  return _jsx('div', {
    style: {
      display: 'flex', gap: '8px', alignItems: 'center', padding: '6px 0',
      borderBottom: `1px solid ${T.border}`, fontSize: '12px',
    },
    children,
  })
}

const COL = {
  grow: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  size: { width: '84px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' },
  risk: { width: '76px' },
  act: { width: '112px', textAlign: 'right' },
}

// ── data plumbing ─────────────────────────────────────────────────────────
async function get(path) {
  const r = await fetch(`${API}${path}`, { headers: { Accept: 'application/json' } })
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`)
  return r.json()
}
async function post(path, body) {
  const r = await fetch(`${API}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}),
  })
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`)
  return r.json()
}
// ── 1. Drive status ───────────────────────────────────────────────────────
function Gauge({ drive }) {
  const total = Number(drive?.total || 0)
  const free = Number(drive?.free || 0)
  const usedPct = total ? Math.min(100, Math.max(0, ((total - free) / total) * 100)) : 0
  const low = free < 15 * GB
  return _jsxs('div', { children: [
    _jsxs('div', { style: { display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px' }, children: [
      _jsx('span', { style: { fontSize: '22px', fontWeight: 600, color: low ? T.danger : T.text }, children: bytes(free) }),
      _jsx('span', { style: { fontSize: '11px', color: T.muted }, children: `free of ${bytes(total)} · ${bytes(total - free)} used` }),
      low ? _jsx(Badge, { fg: T.danger, bg: 'rgba(185,28,28,.15)', children: 'LOW' }) : null,
    ] }),
    _jsx('div', {
      style: { height: '8px', borderRadius: '1px', background: T.border, overflow: 'hidden' },
      children: _jsx('div', {
        style: { width: `${usedPct}%`, height: '100%', background: low ? T.danger : T.accent, transition: 'width .4s' },
      }),
    }),
  ] })
}

/** 3-minute free-space sparkline. One sample a second, so 180 points. */
function Sparkline({ history }) {
  const w = 320
  const h = 40
  if (history.length < 2) {
    return _jsx('div', { style: { fontSize: '11px', color: T.muted, height: `${h}px` }, children: 'Collecting samples…' })
  }
  const vals = history.map(p => p.free)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = max - min || 1
  const pts = history.map((p, i) => {
    const x = (i / (history.length - 1)) * w
    const y = h - ((p.free - min) / span) * (h - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const delta = vals[vals.length - 1] - vals[0]
  return _jsxs('div', { children: [
    _jsx('svg', {
      width: '100%', height: h, viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: 'none',
      style: { display: 'block' },
      children: _jsx('polyline', {
        points: pts, fill: 'none', stroke: T.accent, strokeWidth: 1.5,
        strokeLinejoin: 'round', strokeLinecap: 'round',
      }),
    }),
    _jsx('div', {
      style: { fontSize: '10px', color: T.muted, marginTop: '2px' },
      children: `${history.length}s window · ${delta >= 0 ? '+' : ''}${bytes(Math.abs(delta))} ${delta >= 0 ? 'freed' : 'consumed'} · span ${bytes(min)}–${bytes(max)}`,
    }),
  ] })
}

// ── 2. Index freshness ────────────────────────────────────────────────────
function IndexSection({ status, selectedRoot, onRescan, busy }) {
  const doneAt = status?.done_at || status?.doneAt || null
  const stale = !doneAt || (Date.now() - timestampMillis(doneAt)) > 30 * 60 * 1000
  const pct = status?.progress != null ? Math.round(Number(status.progress) * 100) : null
  const indexedRoot = status?.root || 'not indexed'
  const mismatch = status?.root && !rootsMatch(status.root, selectedRoot)
  return _jsx(Card, {
    title: '2 · Index freshness',
    hint: 'Every number below comes from this index. A stale index gives stale advice.',
    right: _jsx(Btn, { onClick: onRescan, disabled: busy, kind: 'primary', children: busy ? 'Rescanning…' : 'Rescan now' }),
    children: _jsxs('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', fontSize: '12px' }, children: [
      _jsx(Badge, {
        fg: stale ? T.warn : T.ok,
        bg: stale ? 'rgba(246,185,74,.12)' : 'rgba(53,208,111,.12)',
        children: stale ? 'STALE' : 'FRESH',
      }),
      _jsx('span', { children: `Last full index: ${ago(doneAt)}` }),
      _jsx('span', { style: { color: T.muted }, children: `· indexed ${indexedRoot}` }),
      pct !== null && pct < 100 ? _jsx('span', { style: { color: T.muted }, children: `· indexing ${pct}%` }) : null,
      status?.files != null ? _jsx('span', { style: { color: T.muted }, children: `· ${Number(status.files).toLocaleString()} files` }) : null,
      stale ? _jsx('span', { style: { color: T.warn }, children: '— rescan before acting on the targets below.' }) : null,
      mismatch ? _jsx('span', { style: { color: T.warn }, children: `· live gauge is ${selectedRoot}; scan it before cleanup.` }) : null,
    ] }),
  })
}

// ── 3. Folder tree ────────────────────────────────────────────────────────
function TreeSection({ root, noteFor }) {
  const [path, setPath] = useState(root || 'C:\\')
  const [input, setInput] = useState(root || 'C:\\')
  const [node, setNode] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    const next = root || 'C:\\'
    setPath(next)
    setInput(next)
    setNode(null)
    setErr('')
  }, [root])

  useEffect(() => {
    let live = true
    get(`/tree?path=${encodeURIComponent(path)}`)
      .then(d => { if (live) { setNode(d); setErr(d?.engineDown ? 'Engine is not running.' : '') } })
      .catch(e => { if (live) setErr(String(e.message)) })
    return () => { live = false }
  }, [path])

  const children = node?.children || []
  const up = () => {
    const trimmed = path.replace(/\\+$/, '')
    const cut = trimmed.lastIndexOf('\\')
    if (cut > 2) setPath(trimmed.slice(0, cut))
    else setPath(root || 'C:\\')
  }

  return _jsx(Card, {
    title: '3 · Folder tree',
    hint: 'On disk is what deleting gives back. Cloud-only is already reclaimed.',
    right: _jsxs(_Fragment, { children: [
      _jsx('input', {
        value: input, onChange: e => setInput(e.target.value),
        onKeyDown: e => { if (e.key === 'Enter') setPath(input) },
        spellCheck: false,
        style: {
          background: T.bg, color: T.text, border: `1px solid ${T.border}`,
          borderRadius: '2px', padding: '4px 10px', fontSize: '11px', width: '230px',
        },
      }),
      _jsx(Btn, { onClick: () => setPath(input), children: 'Go' }),
      _jsx(Btn, { onClick: up, children: '↑ Up' }),
    ] }),
    children: _jsxs('div', { children: [
      _jsx('div', { style: { fontSize: '11px', color: T.muted, marginBottom: '4px' }, children: path }),
      err ? _jsx('div', { style: { fontSize: '11px', color: T.danger }, children: err }) : null,
      _jsx(Table, {
        head: [
          { label: 'Folder', style: COL.grow },
          { label: 'On disk', style: COL.size },
          { label: 'Cloud only', style: COL.size },
          { label: '', style: COL.act },
        ],
        empty: err ? 'Nothing to show.' : 'No children indexed here.',
        rows: children.slice(0, 40).map(c => {
          const childPath = c.path || `${path.replace(/\\+$/, '')}\\${c.name}`
          const note = noteFor(childPath)
          return _jsxs('div', { children: [
            _jsxs(Row, { children: [
              _jsx('button', {
                onClick: () => { setPath(childPath); setInput(childPath) },
                style: { ...COL.grow, background: 'none', border: 'none', color: T.accent, textAlign: 'left', cursor: 'pointer', fontSize: '12px', padding: 0 },
                children: c.name || childPath,
              }),
              _jsx('span', { style: COL.size, children: bytes(c.on_disk ?? c.onDisk ?? c.bytes) }),
              _jsx('span', { style: { ...COL.size, color: T.muted }, children: bytes(c.cloud_only ?? c.cloudOnly ?? 0) }),
              _jsx('span', { style: COL.act, children: c.dirs || c.files ? _jsx('span', { style: { fontSize: '10px', color: T.muted }, children: `${c.files || 0} files` }) : null }),
            ] }),
            note ? _jsx('div', {
              style: { fontSize: '10px', color: T.muted, padding: '0 0 6px 2px' },
              children: `↳ ${note.note}${note.safeToDelete === true ? ' · safe to delete' : note.safeToDelete === false ? ' · do NOT delete' : ''}`,
            }) : null,
          ] }, childPath)
        }),
      }),
    ] }),
  })
}

// ── 4. Biggest files / by extension ───────────────────────────────────────
function BiggestFiles({ top }) {
  return _jsx(Card, {
    title: '4a · Biggest individual files',
    hint: 'The single files worth looking at before deleting a whole tree.',
    children: _jsx(Table, {
      head: [{ label: 'File', style: COL.grow }, { label: 'On disk', style: COL.size }],
      empty: 'No file list yet — rescan the index.',
      rows: (top || []).slice(0, 15).map((f, i) => _jsxs(Row, { children: [
        _jsx('span', { style: COL.grow, title: f.path, children: f.path }),
        _jsx('span', { style: COL.size, children: bytes(f.bytes ?? f.on_disk) }),
      ] }, `${f.path}-${i}`)),
    }),
  })
}

function ByExtension({ ext }) {
  const rows = (ext || []).slice(0, 12)
  const max = rows.length ? Math.max(...rows.map(e => Number(e.bytes || 0))) : 1
  return _jsx(Card, {
    title: '4b · Size by type',
    hint: 'Which kind of file is eating the volume.',
    children: _jsx(Table, {
      head: [{ label: 'Extension', style: { width: '90px' } }, { label: '', style: COL.grow }, { label: 'On disk', style: COL.size }],
      empty: 'No extension breakdown yet — rescan the index.',
      rows: rows.map(e => _jsxs(Row, { children: [
        _jsx('span', { style: { width: '90px' }, children: e.ext || e.extension || '(none)' }),
        _jsx('span', { style: COL.grow, children: _jsx('span', {
          style: {
            display: 'block', height: '6px', borderRadius: '1px', background: T.accent,
            width: `${Math.max(2, (Number(e.bytes || 0) / max) * 100)}%`, opacity: 0.65,
          },
        }) }),
        _jsx('span', { style: COL.size, children: bytes(e.bytes) }),
      ] }, e.ext || e.extension)),
    }),
  })
}

// ── 5. Reclaim targets ────────────────────────────────────────────────────
function TargetsSection({ targets, onPurge, purging, noteFor, disabled }) {
  const list = targets || []
  const byRisk = r => list.filter(t => (t.risk || 'review') === r)
  return _jsx(Card, {
    title: '5 · Reclaim targets',
    hint: 'Grouped by risk tier. Respect the tiers — they are the engine\u2019s contract, not advice.',
    right: _jsx('span', { style: { fontSize: '10px', color: T.muted }, children: `${list.length} candidates` }),
    children: _jsx('div', { children: ['safe', 'review', 'danger'].map(risk => {
      const rows = byRisk(risk)
      if (!rows.length) return null
      const skin = RISK[risk]
      return _jsxs('div', { style: { marginBottom: '10px' }, children: [
        _jsxs('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '2px' }, children: [
          _jsx(Badge, { fg: skin.fg, bg: skin.bg, children: risk.toUpperCase() }),
          _jsx('span', { style: { fontSize: '11px', color: T.muted }, children: skin.help }),
        ] }),
        _jsx(Table, {
          head: [
            { label: 'Target', style: COL.grow },
            { label: 'On disk', style: COL.size },
            { label: '', style: COL.act },
          ],
          empty: 'none',
          rows: rows.map(t => {
            const note = noteFor(t.path || '')
            return _jsxs('div', { children: [
              _jsxs(Row, { children: [
                _jsxs('span', { style: COL.grow, title: t.path, children: [
                  _jsx('span', { children: t.label || t.path }),
                  _jsx('span', { style: { color: T.muted, fontSize: '10px', marginLeft: '6px' }, children: t.path }),
                ] }),
                _jsx('span', { style: COL.size, children: bytes(t.bytes ?? t.on_disk) }),
                _jsx('span', { style: COL.act, children: risk === 'danger'
                  ? _jsx('span', { style: { fontSize: '10px', color: T.muted }, children: 'report only' })
                  : _jsx(Btn, {
                    kind: risk === 'review' ? 'danger' : 'ghost',
                    disabled: disabled || purging === t.id || !t.id,
                    onClick: () => onPurge(t),
                    children: purging === t.id ? 'Emptying…' : 'Empty',
                  }),
                }),
              ] }),
              risk === 'danger' && t.command ? _jsx('div', {
                style: {
                  fontSize: '10px', color: T.muted, fontFamily: 'ui-monospace, monospace',
                  background: T.bg, border: `1px solid ${T.border}`, borderRadius: '4px',
                  padding: '4px 6px', margin: '0 0 6px', userSelect: 'all',
                },
                children: t.command,
              }) : null,
              note ? _jsx('div', { style: { fontSize: '10px', color: T.muted, padding: '0 0 6px 2px' }, children: `↳ ${note.note}` }) : null,
            ] }, t.id || t.path)
          }),
        }),
      ] }, risk)
    }) }),
  })
}

// ── 6. Sweep ──────────────────────────────────────────────────────────────
function SweepSection({ freeBytes, root, disabled }) {
  const [minFree, setMinFree] = useState(25)
  const [plan, setPlan] = useState(null)
  const [running, setRunning] = useState(false)
  const [armed, setArmed] = useState(false)
  const [err, setErr] = useState('')

  const run = async (dry) => {
    if (disabled) return
    setRunning(true); setErr('')
    try {
      const d = await post('/sweep', { min_free_gb: Number(minFree), dry_run: dry })
      setPlan({ dry, ...d })
      if (!dry) setArmed(false)
    } catch (e) { setErr(String(e.message)) } finally { setRunning(false) }
  }

  const alreadyAbove = freeBytes != null && freeBytes > Number(minFree) * GB
  const items = sweepItems(plan)

  useEffect(() => {
    setPlan(null)
    setArmed(false)
    setErr('')
  }, [root, disabled])

  return _jsx(Card, {
    title: '6 · Sweep',
    hint: 'Sheds safe, automatable targets until the threshold is met. A no-op when free space is already above it.',
    right: _jsxs(_Fragment, { children: [
      _jsx('span', { style: { fontSize: '11px', color: T.muted }, children: 'min free' }),
      _jsx('input', {
        type: 'number', min: 1, max: 500, value: minFree,
        onChange: e => { setMinFree(e.target.value); setArmed(false); setPlan(null) },
        style: {
          width: '62px', background: T.bg, color: T.text, border: `1px solid ${T.border}`,
          borderRadius: '2px', padding: '4px 10px', fontSize: '11px',
        },
      }),
      _jsx('span', { style: { fontSize: '11px', color: T.muted }, children: 'GB' }),
      _jsx(Btn, { onClick: () => run(true), disabled: disabled || running, children: running ? 'Working…' : 'Dry run' }),
      armed
        ? _jsx(Btn, { kind: 'danger', onClick: () => run(false), disabled: disabled || running, children: 'Confirm real sweep' })
        : _jsx(Btn, { onClick: () => setArmed(true), disabled: disabled || running || !plan || plan.dry !== true, title: plan ? '' : 'Dry-run first', children: 'Real sweep…' }),
    ] }),
    children: _jsxs('div', { style: { fontSize: '12px' }, children: [
      disabled ? _jsx('div', { style: { fontSize: '11px', color: T.warn, marginBottom: '4px' }, children: 'Scan the selected drive before running cleanup.' }) : null,
      alreadyAbove ? _jsx('div', { style: { fontSize: '11px', color: T.muted, marginBottom: '4px' }, children: `${String(root || '').replace(/\\+$/, '')} already has more than ${minFree} GB free, so a sweep at this threshold does nothing.` }) : null,
      err ? _jsx('div', { style: { fontSize: '11px', color: T.danger }, children: err }) : null,
      !plan ? _jsx('div', { style: { fontSize: '11px', color: T.muted }, children: 'Dry-run first. The real sweep only unlocks after you have seen the plan.' })
        : _jsxs('div', { children: [
          _jsxs('div', { style: { marginBottom: '4px' }, children: [
            _jsx(Badge, {
              fg: plan.dry ? T.warn : T.ok, bg: plan.dry ? 'rgba(246,185,74,.12)' : 'rgba(53,208,111,.12)',
              children: plan.dry ? 'DRY RUN — nothing was deleted' : 'SWEPT',
            }),
            _jsx('span', { style: { marginLeft: '8px', color: T.muted, fontSize: '11px' }, children: `${bytes(sweepTotalBytes(plan))} across ${items.length} target(s)` }),
          ] }),
          _jsx(Table, {
            head: [{ label: 'Target', style: COL.grow }, { label: 'Bytes', style: COL.size }],
            empty: 'Nothing eligible at this threshold.',
            rows: items.slice(0, 20).map((t, i) => _jsxs(Row, { children: [
              _jsx('span', { style: COL.grow, title: t.path, children: t.label || t.path || String(t) }),
              _jsx('span', { style: COL.size, children: bytes(sweepItemBytes(t)) }),
            ] }, `${t.id || t.path || i}`)),
          }),
        ] }),
    ] }),
  })
}

// ── 7. Cloud storage, with OneDrive-only state controls ───────────────────
/**
 * The ticker reports the REAL C: free delta, not the file attributes.
 * Dehydration only frees bytes OneDrive has already finished uploading, so a
 * folder can accept the flag and free nothing — attributes would report success
 * while nothing moved. Free space is the only honest signal, so that is what is
 * shown, and the panel says so when it has not moved.
 */
function CloudStorageSection({ freeBytes, cloud }) {
  const [path, setPath] = useState('')
  const [op, setOp] = useState(null) // {mode, startedAt, startFree}
  const [tick, setTick] = useState(0)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')
  const providers = cloud?.providers || []
  const oneDrive = providers.find(p => p.id === 'onedrive')
  const canPin = providerAllowsPin(oneDrive)

  useEffect(() => {
    if (!path && oneDrive?.roots?.[0]?.path) setPath(oneDrive.roots[0].path)
  }, [oneDrive, path])

  useEffect(() => {
    if (!op) return undefined
    const id = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(id)
  }, [op])

  const start = async (mode) => {
    if (!canPin) { setErr('No active OneDrive root supports this action.'); return }
    if (!path.trim()) { setErr('Give a OneDrive folder path first.'); return }
    setErr(''); setResult(null)
    setOp({ mode, startedAt: Date.now(), startFree: freeBytes ?? 0 })
    try {
      const d = await post('/pin', { path: path.trim(), mode })
      setResult(d)
    } catch (e) {
      setErr(String(e.message))
    }
  }

  const elapsed = op ? (Date.now() - op.startedAt) / 1000 : 0
  const delta = op && freeBytes != null ? freeBytes - op.startFree : 0
  const stalled = op && elapsed > 120 && Math.abs(delta) < 64 * 1024 * 1024

  return _jsx(Card, {
    title: '7 · Cloud storage',
    hint: 'Measured roots for OneDrive and Google Drive. State changes remain provider-specific.',
    right: canPin ? _jsxs(_Fragment, { children: [
      _jsx('input', {
        value: path, onChange: e => setPath(e.target.value), spellCheck: false,
        placeholder: 'OneDrive folder path',
        style: {
          background: T.bg, color: T.text, border: `1px solid ${T.border}`,
          borderRadius: '2px', padding: '4px 10px', fontSize: '11px', width: '280px',
        },
      }),
      _jsx(Btn, { onClick: () => start('free'), disabled: !!op && !result, children: 'Free up space' }),
      _jsx(Btn, { onClick: () => start('pin'), disabled: !!op && !result, children: 'Keep on device' }),
    ] }) : _jsx(Badge, { fg: T.muted, bg: 'rgba(107,114,128,.15)', children: 'MEASURE ONLY' }),
    children: _jsxs('div', { style: { fontSize: '12px' }, children: [
      _jsx('div', {
        style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '8px', marginBottom: '10px' },
        children: providers.map(provider => _jsxs('div', {
          style: { background: T.bg, border: `1px solid ${T.border}`, borderRadius: '6px', padding: '10px' },
          children: [
            _jsxs('div', { style: { display: 'flex', gap: '7px', alignItems: 'center', marginBottom: '5px' }, children: [
              _jsx('strong', { children: provider.name }),
              _jsx(Badge, {
                fg: provider.installed ? T.ok : T.muted,
                bg: provider.installed ? 'rgba(4,120,87,.15)' : 'rgba(107,114,128,.15)',
                children: provider.installed ? 'INSTALLED' : 'NOT FOUND',
              }),
              provider.measure_only ? _jsx(Badge, { fg: T.warn, bg: 'rgba(246,185,74,.12)', children: 'MEASURE ONLY' }) : null,
            ] }),
            _jsx('div', { style: { fontSize: '10px', color: T.muted, marginBottom: '5px' }, children: provider.note }),
            _jsx(Table, {
              head: [{ label: 'Root', style: COL.grow }, { label: 'Local bytes', style: COL.size }],
              empty: provider.installed ? 'Installed, but no active root is mounted or configured.' : 'Provider is not installed.',
              rows: (provider.roots || []).map(root => _jsxs(Row, { children: [
                _jsxs('span', { style: COL.grow, title: root.path, children: [root.title || provider.name, _jsx('span', { style: { color: T.muted, fontSize: '10px', marginLeft: '6px' }, children: root.path })] }),
                _jsx('span', { style: COL.size, children: root.local_bytes == null ? 'outside index' : bytes(root.local_bytes) }),
              ] }, root.path)),
            }),
            provider.cache ? _jsxs('div', { style: { fontSize: '10px', color: T.muted, marginTop: '5px' }, children: [
              'DriveFS cache: ', provider.cache.local_bytes == null ? 'scan pending' : bytes(provider.cache.local_bytes),
            ] }) : null,
          ],
        }, provider.id)),
      }),
      _jsx('div', {
        style: { fontSize: '11px', color: T.muted, marginBottom: '6px', lineHeight: 1.5 },
        children: canPin ? 'OneDrive dehydration only frees bytes already uploaded. The ticker measures the actual C: free-space delta. Google Drive stays measure-only because Drive for desktop does not expose a supported equivalent command.' : 'Google Drive is installed but has no active root. Start Drive for desktop to mount it; Drive Sentinel will discover it on the next refresh.',
      }),
      err ? _jsx('div', { style: { fontSize: '11px', color: T.danger, marginBottom: '4px' }, children: err }) : null,
      op ? _jsxs('div', {
        style: {
          display: 'flex', gap: '18px', flexWrap: 'wrap', alignItems: 'baseline',
          background: T.bg, border: `1px solid ${T.border}`, borderRadius: '6px', padding: '10px',
        },
        children: [
          _jsx(Badge, { children: op.mode === 'free' ? 'DEHYDRATING' : 'REHYDRATING' }),
          _jsxs('span', { children: [_jsx('span', { style: { color: T.muted }, children: 'C: free delta ' }), _jsx('span', {
            style: { fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: delta > 0 ? T.ok : delta < 0 ? T.warn : T.text },
            children: `${delta >= 0 ? '+' : '−'}${bytes(Math.abs(delta))}`,
          })] }),
          _jsxs('span', { children: [_jsx('span', { style: { color: T.muted }, children: 'C: free now ' }), bytes(freeBytes)] }),
          _jsxs('span', { children: [_jsx('span', { style: { color: T.muted }, children: 'elapsed ' }), clock(elapsed)] }),
          result ? _jsx(Badge, { fg: T.ok, bg: 'rgba(4,120,87,.15)', children: 'ENGINE REPORTED DONE' }) : _jsx('span', { style: { color: T.muted }, children: 'engine working…' }),
          _jsx(Btn, { onClick: () => { setOp(null); setResult(null) }, children: 'Clear' }),
        ],
      }) : null,
      stalled ? _jsx('div', {
        style: { marginTop: '6px', fontSize: '11px', color: T.warn },
        children: 'Free space has not moved in over two minutes. OneDrive has probably not finished uploading this folder, so nothing can be freed yet — stop retrying, and if this is regenerable build output, delete it instead.',
      }) : null,
    ] }),
  })
}

// ── 8. Scheduling ─────────────────────────────────────────────────────────
function ScheduleSection() {
  return _jsx(Card, {
    title: '8 · Automation boundary',
    hint: 'Drive Sentinel never invents cleanup targets or edits scheduler files through an agent prompt.',
    right: _jsx(Badge, { fg: T.warn, bg: 'rgba(246,185,74,.12)', children: 'GUARDED' }),
    children: _jsx('div', {
      style: { fontSize: '11px', color: T.muted, lineHeight: 1.6 },
      children: 'Unattended sweeps are limited to safe targets on the Windows system drive. Use the reclaim panel for a dry run and explicit execution; review and danger tiers remain report-only.',
    }),
  })
}

// ── 9. Project memory ─────────────────────────────────────────────────────
function MemorySection({ notes, onSave }) {
  const [path, setPath] = useState('')
  const [note, setNote] = useState('')
  const [safe, setSafe] = useState('unknown')
  const entries = Object.entries(notes || {})

  return _jsx(Card, {
    title: '9 · Project memory',
    hint: 'What each big directory is for, so a future sweep does not have to guess.',
    right: _jsx('span', { style: { fontSize: '10px', color: T.muted }, children: `${entries.length} noted` }),
    children: _jsxs('div', { children: [
      _jsxs('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '8px' }, children: [
        _jsx('input', {
          value: path, onChange: e => setPath(e.target.value), spellCheck: false, placeholder: 'directory path',
          style: { flex: '1 1 240px', background: T.bg, color: T.text, border: `1px solid ${T.border}`, borderRadius: '2px', padding: '4px 10px', fontSize: '11px' },
        }),
        _jsx('input', {
          value: note, onChange: e => setNote(e.target.value), placeholder: 'what it is for (empty = forget it)',
          style: { flex: '2 1 300px', background: T.bg, color: T.text, border: `1px solid ${T.border}`, borderRadius: '2px', padding: '4px 10px', fontSize: '11px' },
        }),
        _jsx('select', {
          value: safe, onChange: e => setSafe(e.target.value),
          style: { background: T.bg, color: T.text, border: `1px solid ${T.border}`, borderRadius: '2px', padding: '4px 10px', fontSize: '11px' },
          children: [
            _jsx('option', { value: 'unknown', children: 'unknown' }, 'u'),
            _jsx('option', { value: 'yes', children: 'safe to delete' }, 'y'),
            _jsx('option', { value: 'no', children: 'do not delete' }, 'n'),
          ],
        }),
        _jsx(Btn, {
          kind: 'primary',
          onClick: () => { onSave(path, note, safe); setPath(''); setNote(''); setSafe('unknown') },
          disabled: !path.trim(),
          children: 'Save note',
        }),
      ] }),
      _jsx(Table, {
        head: [{ label: 'Directory', style: COL.grow }, { label: 'Note', style: { flex: 2, minWidth: 0 } }, { label: '', style: COL.risk }],
        empty: 'No notes yet. The hourly job seeds these from C:\\build\\README.md when it exists.',
        rows: entries.slice(0, 30).map(([k, v]) => _jsxs(Row, { children: [
          _jsx('span', { style: COL.grow, title: k, children: k }),
          _jsx('span', { style: { flex: 2, minWidth: 0, color: T.muted }, children: v?.note }),
          _jsx('span', { style: COL.risk, children: v?.safeToDelete === true
            ? _jsx(Badge, { fg: T.ok, bg: 'rgba(4,120,87,.15)', children: 'SAFE' })
            : v?.safeToDelete === false
              ? _jsx(Badge, { fg: T.danger, bg: 'rgba(185,28,28,.15)', children: 'KEEP' })
              : null }),
        ] }, k)),
      }),
    ] }),
  })
}

// ── engine-down card ──────────────────────────────────────────────────────
function EngineDown({ detail }) {
  return _jsx('div', {
    style: {
      background: T.card, border: `1px solid ${T.danger}`, borderRadius: '2px',
      padding: '14px', marginBottom: '12px',
    },
    children: _jsxs('div', { style: { display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }, children: [
      _jsx(Badge, { fg: T.danger, bg: 'rgba(185,28,28,.15)', children: 'ENGINE NOT RUNNING' }),
      _jsx('span', { style: { fontSize: '12px' }, children: 'The bundled Drive Sentinel service is unavailable. Restart Codex Crew to let the app manager recover it.' }),
      detail ? _jsx('span', { style: { fontSize: '10px', color: T.muted }, children: detail }) : null,
    ] }),
  })
}

// ── panel ─────────────────────────────────────────────────────────────────
export default function DriveSentinelPanel() {
  const [drive, setDrive] = useState(null)
  const [systemDrive, setSystemDrive] = useState(null)
  const [volumes, setVolumes] = useState([])
  const [selectedRoot, setSelectedRoot] = useState('C:\\')
  const [cloud, setCloud] = useState(null)
  const [status, setStatus] = useState(null)
  const [targets, setTargets] = useState([])
  const [top, setTop] = useState([])
  const [ext, setExt] = useState([])
  const [notes, setNotes] = useState({})
  const [history, setHistory] = useState([])
  const [down, setDown] = useState(null)
  const [scanning, setScanning] = useState(false)
  const [purging, setPurging] = useState('')
  const [tab, setTab] = useState('reclaim')
  const rootRef = useRef(null)

  // One second cadence for the gauge and the sparkline; the heavier reads only
  // refresh every 30s so a panel left open does not hammer the index.
  useEffect(() => {
    let live = true
    setHistory([])
    const pollDrive = async () => {
      try {
        const d = await get(`/drive?root=${encodeURIComponent(selectedRoot)}`)
        if (!live) return
        if (d?.engineDown) { setDown(d.detail || 'unreachable'); return }
        setDown(null)
        setDrive(d)
        if (rootsMatch(selectedRoot, 'C:\\')) {
          setSystemDrive(d)
        } else {
          const system = await get(`/drive?root=${encodeURIComponent('C:\\')}`)
          if (live && !system?.engineDown) setSystemDrive(system)
        }
        const free = Number(d.free || 0)
        setHistory(h => [...h, { t: Date.now(), free }].slice(-180))
      } catch (e) { if (live) setDown(String(e.message)) }
    }
    pollDrive()
    const id = setInterval(pollDrive, 1000)
    return () => { live = false; clearInterval(id) }
  }, [selectedRoot])

  const loadHeavy = useCallback(async () => {
    const settle = async (p, set) => { try { const d = await p; if (!d?.engineDown) set(d) } catch { /* engine-down card covers it */ } }
    await Promise.all([
      settle(get('/status'), setStatus),
      settle(get('/volumes'), d => {
        const list = d.volumes || []
        setVolumes(list)
        setSelectedRoot(current => {
          if (list.some(volume => rootsMatch(volume.root, current))) return current
          if (list.some(volume => rootsMatch(volume.root, d.indexed_root))) return d.indexed_root
          return list[0]?.root || current
        })
      }),
      settle(get('/cloud'), setCloud),
      settle(get('/targets'), d => setTargets(d.targets || d || [])),
      settle(get('/top'), d => setTop(d.files || d.top || d || [])),
      settle(get('/ext'), d => setExt(d.ext || d.extensions || d || [])),
      settle(get('/memory'), d => setNotes(d.notes || {})),
    ])
  }, [])

  useEffect(() => {
    loadHeavy()
    const id = setInterval(loadHeavy, 30000)
    return () => clearInterval(id)
  }, [loadHeavy])

  const noteFor = useCallback((p) => {
    if (!p) return null
    const key = Object.keys(notes).find(k => k.toLowerCase() === p.toLowerCase())
    return key ? notes[key] : null
  }, [notes])

  const saveNote = async (p, note, safe) => {
    const safeToDelete = safe === 'yes' ? true : safe === 'no' ? false : null
    try {
      const d = await post('/memory', { path: p.trim(), note, safeToDelete })
      setNotes(d.notes || {})
    } catch { /* surfaced by the next poll */ }
  }

  const rescan = async () => {
    setScanning(true)
    try {
      const started = await post('/scan', { root: selectedRoot })
      setStatus(current => ({ ...(current || {}), root: started.root, scanning: true, done_at: 0, has_index: false }))
      setTargets([])
      setTop([])
      setExt([])
    } catch { /* engine-down card covers it */ }
    setTimeout(() => { setScanning(false); loadHeavy() }, 4000)
  }

  const purge = async (t) => {
    setPurging(t.id)
    try { await post('/purge', { id: t.id }) } catch { /* engine reports its own refusal */ }
    setPurging(''); loadHeavy()
  }

  const freeBytes = drive ? Number(drive.free || 0) : null
  const systemFreeBytes = systemDrive ? Number(systemDrive.free || 0) : null
  const indexedRoot = status?.root || 'C:\\'
  const indexMatchesSelection = rootsMatch(indexedRoot, selectedRoot)
  const cleanupReady = indexMatchesSelection && status?.has_index && !status?.scanning && !scanning
  const totalDeletable = useMemo(
    () => (targets || []).filter(t => t.risk === 'safe').reduce((a, t) => a + Number(t.bytes || t.on_disk || 0), 0),
    [targets],
  )

  const TABS = [
    ['reclaim', 'Reclaim & sweep'],
    ['browse', 'Browse & measure'],
    ['cloud', 'Cloud storage'],
    ['policy', 'Policy & notes'],
  ]

  return _jsxs('div', {
    ref: rootRef,
    // position:relative, never fixed — this mounts into the dashboard DOM, so a
    // fixed child would cover the sidebar and header too.
    style: { position: 'relative', maxWidth: '1200px', margin: '0 auto', padding: '16px', color: T.text, fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace' },
    children: [
      // header
      _jsxs('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', marginBottom: '16px', flexWrap: 'wrap' }, children: [
        _jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' }, children: [
          _jsx('div', { style: { color: T.accent, border: `1px solid ${T.accent}`, borderRadius: '2px', padding: '2px 5px', fontWeight: 800, fontSize: '13px' }, children: '>_' }),
          _jsx('h2', { style: { margin: 0, fontSize: '17px', letterSpacing: '.04em' }, children: 'DRIVE SENTINEL' }),
          _jsx(Badge, { children: 'LIVE INDEX' }),
        ] }),
        _jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' }, children: [
          _jsx('span', { style: { fontSize: '11px', color: T.muted }, children: totalDeletable ? `${bytes(totalDeletable)} safely reclaimable` : '' }),
          _jsx(Btn, { onClick: loadHeavy, children: '↻ Refresh' }),
          _jsx('span', { style: { fontSize: '10px', color: T.muted }, children: 'CODEX EDITION · 1.3.0' }),
        ] }),
      ] }),

      down ? _jsx(EngineDown, { detail: down }) : null,

      // 1 · Drive status
      _jsx(Card, {
        title: '1 · Drive status',
        hint: 'Selected volume, measured live each second. Selection alone never starts a scan.',
        right: _jsx('select', {
          'aria-label': 'Drive to measure and index',
          value: selectedRoot,
          onChange: event => setSelectedRoot(event.target.value),
          style: {
            background: T.bg, color: T.text, border: `1px solid ${T.border}`,
            borderRadius: '2px', padding: '5px 10px', fontSize: '11px',
          },
          children: volumes.length
            ? volumes.map(volume => _jsx('option', { value: volume.root, children: volumeOptionLabel(volume) }, volume.root))
            : _jsx('option', { value: selectedRoot, children: selectedRoot }),
        }),
        children: _jsxs('div', { style: { display: 'flex', gap: '24px', flexWrap: 'wrap', alignItems: 'flex-end' }, children: [
          _jsx('div', { style: { flex: '1 1 260px' }, children: _jsx(Gauge, { drive }) }),
          _jsx('div', { style: { flex: '1 1 320px' }, children: _jsx(Sparkline, { history }) }),
        ] }),
      }),

      _jsx(IndexSection, { status, selectedRoot, onRescan: rescan, busy: scanning || status?.scanning }),

      // tabs
      _jsx('div', { style: { display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap' }, children: TABS.map(([id, label]) => _jsx('button', {
        onClick: () => setTab(id),
        style: {
          borderRadius: '2px', fontSize: '10px', fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', padding: '6px 12px', cursor: 'pointer',
          background: tab === id ? 'rgba(53,208,111,.12)' : 'transparent',
          color: tab === id ? T.text : T.muted,
          border: `1px solid ${tab === id ? T.accent : T.border}`,
        },
        children: label,
      }, id)) }),

      tab === 'reclaim' ? _jsxs(_Fragment, { children: [
        _jsx(TargetsSection, { targets, onPurge: purge, purging, noteFor, disabled: !cleanupReady }),
        _jsx(SweepSection, { freeBytes: cleanupReady ? freeBytes : null, root: indexedRoot, disabled: !cleanupReady }),
      ] }) : null,

      tab === 'browse' ? _jsxs(_Fragment, { children: [
        _jsx(TreeSection, { root: indexedRoot, noteFor }),
        _jsx(BiggestFiles, { top }),
        _jsx(ByExtension, { ext }),
      ] }) : null,

      tab === 'cloud' ? _jsx(CloudStorageSection, { freeBytes: systemFreeBytes, cloud }) : null,

      tab === 'policy' ? _jsxs(_Fragment, { children: [
        _jsx(ScheduleSection, {}),
        _jsx(MemorySection, { notes, onSave: saveNote }),
      ] }) : null,
    ],
  })
}
