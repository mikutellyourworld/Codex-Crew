import { TerminalMascot } from '../../components/TerminalMascot'

/** Legacy component name kept for theme compatibility. */
export function GhostVar1({ width = 52 }: { width?: number }) {
  return <TerminalMascot size={width} className="text-text-strong" />
}

/** Codex Crew terminal mark used by the feature-education chapters. */
export function GhostWithArm({ width = 92 }: { width?: number }) {
  return <TerminalMascot size={width} className="text-text-strong" />
}
