import { createContext, useContext, type ReactNode } from 'react'
import { getAdapter } from './registry'
import type { ProviderAdapter } from './types'

// ACP is the single transport adapter; backend selection happens separately.
// The context is retained (rather than
// inlining the adapter at each call site) so the many useProvider() consumers
// stay unchanged.
const acpAdapter = getAdapter()

const ProviderContext = createContext<ProviderAdapter>(acpAdapter)

export function ProviderProvider({ children }: { children: ReactNode }) {
  return <ProviderContext.Provider value={acpAdapter}>{children}</ProviderContext.Provider>
}

export function useProvider(): ProviderAdapter {
  return useContext(ProviderContext)
}
