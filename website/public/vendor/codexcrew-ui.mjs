// Vendor stub: re-exports @codexcrew/ui from the host.
const m = window.__codexcrew_modules?.['@codexcrew/ui']
if (!m) throw new Error('[vendor/codexcrew-ui] Host modules not initialized.')
export const {
  Card, CardTitle, Btn, SendBtn, Input, SearchInput,
  Badge, AimBadge, StatCard, Skeleton, ContentSkeleton,
  EmptyState, PageHeader, Toggle, InfoTip, SegmentedControl,
  MarkdownRenderer,
} = m
