import type { ReactNode } from 'react'
import { useRefreshScheduler } from '../hooks/useRefreshScheduler'

export default function DashboardBootstrap({ children }: { children: ReactNode }) {
  // Public builds do not require kiro-cli. Backend readiness is shown where the
  // user selects Codex or an authenticated OpenAI-compatible profile.
  useRefreshScheduler()
  return children
}
