interface TerminalMascotProps {
  size?: number
  className?: string
}

/** Codex Crew terminal mark for welcome and onboarding surfaces. */
export function TerminalMascot({ size = 40, className = '' }: TerminalMascotProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <rect x="4" y="7" width="56" height="50" rx="11" fill="#0a0f12" stroke="currentColor" strokeWidth="2.5" />
      <path d="M4 20h56" stroke="currentColor" strokeOpacity=".32" strokeWidth="2" />
      <circle cx="13" cy="14" r="2.2" fill="#7c3aed" />
      <circle cx="21" cy="14" r="2.2" fill="currentColor" fillOpacity=".28" />
      <circle cx="29" cy="14" r="2.2" fill="currentColor" fillOpacity=".28" />
      <path d="m17 31 8 7-8 7" stroke="#c9ff38" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M31 45h16" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  )
}
