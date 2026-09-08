/**
 * Terminal frames used by the chat loading carousel.
 *
 * The legacy export names remain as an internal compatibility seam for themes,
 * while every visible frame now uses the Codex Crew terminal mark.
 */
import terminalMark from '../assets/terminal-mark.svg'

export const GHOST_POSE_URLS: string[] = Array.from({ length: 8 }, () => terminalMark)

export function GhostPose({ src }: { src: string }) {
  return <img className="kp" src={src} alt="" aria-hidden="true" draggable={false} />
}

export const GHOST_POSE_ICONS = GHOST_POSE_URLS.map(
  src => function TerminalFrameIcon() { return <GhostPose src={src} /> }
)
