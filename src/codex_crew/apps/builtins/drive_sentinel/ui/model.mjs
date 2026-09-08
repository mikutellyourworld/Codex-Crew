export function sweepItems(plan) {
  if (Array.isArray(plan?.purged)) return plan.purged
  if (Array.isArray(plan?.targets)) return plan.targets
  if (Array.isArray(plan?.actions)) return plan.actions
  return []
}

export function sweepTotalBytes(plan) {
  return Number(plan?.freed ?? plan?.bytes ?? plan?.total_bytes ?? 0)
}

export function sweepItemBytes(item) {
  return Number(item?.freed ?? item?.would_free ?? item?.bytes ?? 0)
}

export function providerAllowsPin(provider) {
  return provider?.id === 'onedrive'
    && provider?.supports_pin === true
    && provider?.measure_only !== true
}

export function timestampMillis(value) {
  if (typeof value === 'number') return value < 1_000_000_000_000 ? value * 1000 : value
  return new Date(value).getTime()
}

export function rootsMatch(left, right) {
  return String(left || '').replaceAll('/', '\\').toUpperCase()
    === String(right || '').replaceAll('/', '\\').toUpperCase()
}

export function volumeOptionLabel(volume) {
  const root = String(volume?.root || '').replace(/\\+$/, '')
  const label = String(volume?.label || '').trim()
  const kind = String(volume?.kind || 'volume')
  const gb = Number(volume?.free || 0) / (1024 ** 3)
  const free = `${gb < 10 ? gb.toFixed(1) : Math.round(gb)} GB free`
  return [root, label, '·', kind, '·', free].filter(Boolean).join(' ')
}

export function ageLabel(value, now = Date.now()) {
  if (!value) return 'never'
  const ms = now - timestampMillis(value)
  if (Number.isNaN(ms)) return String(value)
  const minutes = Math.max(0, Math.floor(ms / 60000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`
}
