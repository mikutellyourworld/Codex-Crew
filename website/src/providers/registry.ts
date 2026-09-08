import type { ProviderAdapter, ProviderId } from './types'
import { AcpAdapter } from './adapters/acp'

// ACP is the sole transport (agent.provider enum is ["acp"]), while the agent
// backend selects Codex or an authenticated OpenAI-compatible profile. The
// adapter registry therefore has a single entry; it stays as a thin indirection so pages that consume
// useProvider()/the adapter interface for labels/capabilities/model-windows
// stay unchanged.
const ADAPTERS: Record<ProviderId, ProviderAdapter> = {
  acp: new AcpAdapter(),
}

export function getAdapter(_id?: ProviderId): ProviderAdapter {
  return ADAPTERS.acp
}
