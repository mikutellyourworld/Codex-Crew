import { BrandGlyph } from './BrandIcon'
import terminalMarkUrl from '../assets/terminal-mark.svg'

/** Monochrome Codex Crew terminal glyph for compact navigation surfaces. */
export function CodexCrewMark({
  size = 16,
  className = 'inline-block shrink-0',
}: {
  size?: number
  className?: string
}) {
  return (
    <BrandGlyph
      url={terminalMarkUrl}
      size={size}
      className={className}
      testId="codex-crew-terminal-mark"
    />
  )
}
