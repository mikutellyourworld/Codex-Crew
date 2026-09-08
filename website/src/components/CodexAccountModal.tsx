import { AlertCircle, CheckCircle2, Code2, ExternalLink, Loader2, TerminalSquare } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { api, type AcpBackendProbe } from '../api/client'
import { i18nT } from '../i18n/t'
import { AgentBackendTab } from '../pages/developer/AgentBackendTab'
import Modal from './Modal'

const CODEX_CLI_DOCS_URL = 'https://developers.openai.com/codex/cli/'

interface CodexAccountModalProps {
  open: boolean
  onClose: () => void
  status?: AcpBackendProbe
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border py-2 last:border-b-0">
      <span className="text-[12px] text-muted">{label}</span>
      <span className="text-right text-[13px] font-medium text-text">{value}</span>
    </div>
  )
}

export default function CodexAccountModal({ open, onClose, status }: CodexAccountModalProps) {
  const { data } = useQuery({
    queryKey: ['acp-backends'],
    queryFn: api.acpBackends,
    enabled: open && status === undefined,
  })
  const resolvedStatus = status ?? data?.backends?.find(backend => backend.id === 'codex')
  const installed = resolvedStatus?.installed === 'installed'
  const missing = resolvedStatus?.installed === 'missing'

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={(
        <span className="flex items-center gap-2">
          <Code2 className="lucide-inline" />
          {i18nT('pages.developer.agentBackendTab.codex_cli')}
        </span>
      )}
      maxWidth={680}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col items-center px-4 py-3 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full border border-accent/30 bg-accent/10 text-accent shadow-sm">
            <TerminalSquare className="h-6 w-6" strokeWidth={1.7} />
          </div>
          <div className="mt-3 flex items-center justify-center gap-2 text-[14px] font-semibold text-text-strong">
            {!resolvedStatus ? (
              <><Loader2 className="lucide-inline animate-spin" /> {i18nT('components.codexAccountModal.checking')}</>
            ) : installed ? (
              <><CheckCircle2 className="lucide-inline text-success" /> {i18nT('components.codexAccountModal.ready')}</>
            ) : (
              <><AlertCircle className="lucide-inline text-warn" /> {i18nT('components.codexAccountModal.needs_setup')}</>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-border px-3">
          <DetailRow
            label={i18nT('components.codexAccountModal.role')}
            value={i18nT('components.codexAccountModal.primary_backend')}
          />
          <DetailRow
            label={i18nT('components.codexAccountModal.status')}
            value={!resolvedStatus
              ? i18nT('components.codexAccountModal.checking_short')
              : installed
                ? i18nT('components.codexAccountModal.installed')
                : missing
                  ? i18nT('components.codexAccountModal.missing')
                  : i18nT('components.codexAccountModal.unknown')}
          />
        </div>

        <div className="rounded-lg border border-border bg-bg-elevated/40 p-3.5 text-[13px] leading-relaxed text-muted">
          {i18nT('components.codexAccountModal.auth_help', { command: 'codex login' })}
        </div>

        <AgentBackendTab />

        {missing && resolvedStatus && resolvedStatus.missing_components.length > 0 && (
          <div className="rounded-lg border border-warn/30 bg-warn/5 p-3.5">
            <div className="mb-2 text-[12px] font-medium text-text">
              {i18nT('components.codexAccountModal.missing_components')}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {resolvedStatus.missing_components.map(component => (
                <code key={component} className="rounded bg-bg px-2 py-1 font-mono text-[11px] text-text">
                  {component}
                </code>
              ))}
            </div>
            {resolvedStatus.install_command && (
              <code className="mt-3 block overflow-x-auto rounded bg-bg p-2 font-mono text-[11px] text-text">
                {resolvedStatus.install_command}
              </code>
            )}
          </div>
        )}

        <a
          href={CODEX_CLI_DOCS_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 self-start text-[12px] text-accent hover:underline"
        >
          {i18nT('components.codexAccountModal.documentation')} <ExternalLink className="lucide-inline" />
        </a>
      </div>
    </Modal>
  )
}
