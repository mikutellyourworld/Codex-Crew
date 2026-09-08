import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { patchConfigMock, codexcrewConfigMock, schemaMock, acpBackendsMock, installCodexMock } = vi.hoisted(() => ({
  patchConfigMock: vi.fn(() => Promise.resolve({})),
  codexcrewConfigMock: vi.fn(() => Promise.resolve({ agent: { acp_backend: 'codex' } })),
  schemaMock: vi.fn(),
  acpBackendsMock: vi.fn(),
  installCodexMock: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    codexcrewConfig: codexcrewConfigMock,
    patchConfig: patchConfigMock,
    acpBackends: acpBackendsMock,
    installCodex: installCodexMock,
  },
}))

vi.mock('../components/settingRef/useConfigSchema', () => ({
  useConfigSchema: () => schemaMock(),
}))

import { AgentBackendTab } from '../pages/developer/AgentBackendTab'

const PUBLIC = ['codex', 'openai_compatible']

function schemaWith(values: string[] | undefined) {
  return values
    ? new Map([['agent.acp_backend', { path: 'agent.acp_backend', type: 'enum', enum: values }]])
    : undefined
}

function probeRow(id: string, over: Partial<{
  selectable: boolean
  installed: string
  missing_components: string[]
  install_command: string
  restart_required: boolean
  policy_id: string
  codex_cli_source: string
  codex_cli_version: string
  one_click_install: boolean
}> = {}) {
  return {
    id,
    policy_id: id,
    selectable: true,
    installed: 'installed',
    missing_components: [],
    install_command: '',
    restart_required: false,
    codex_cli_source: id === 'codex' ? 'external' : '',
    codex_cli_version: id === 'codex' ? '1.2.3' : '',
    one_click_install: false,
    ...over,
  }
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AgentBackendTab />
    </QueryClientProvider>,
  )
}

const button = (name: string) => screen.getByRole('button', { name })

beforeEach(() => {
  cleanup()
  patchConfigMock.mockReset().mockResolvedValue({})
  codexcrewConfigMock.mockReset().mockResolvedValue({ agent: { acp_backend: 'codex' } })
  schemaMock.mockReset().mockReturnValue(schemaWith(PUBLIC))
  acpBackendsMock.mockReset().mockRejectedValue(new Error('404 Not Found'))
  installCodexMock.mockReset()
})

describe('AgentBackendTab public backends', () => {
  it('offers only Codex and OpenAI-compatible backends', async () => {
    mount()
    const labels = ['Codex CLI', 'OpenAI Compatible']
    await screen.findByRole('button', { name: 'Codex CLI' })
    const rendered = screen.getAllByRole('button').map(node => node.textContent?.trim()).filter(text => text && labels.includes(text))
    expect(rendered).toEqual(labels)
    for (const name of ['Claude Code', 'Kimi CLI', 'Kiro CLI', 'KAS (kiro-agent)']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
  })

  it('uses Codex when old config has no backend field', async () => {
    codexcrewConfigMock.mockResolvedValue({ agent: {} })
    mount()
    expect(await screen.findByRole('button', { name: 'Codex CLI' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('reflects the configured backend and saves a new selection', async () => {
    codexcrewConfigMock.mockResolvedValue({ agent: { acp_backend: 'openai_compatible' } })
    mount()
    expect(await screen.findByRole('button', { name: 'OpenAI Compatible' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(button('Codex CLI'))
    await waitFor(() => expect(patchConfigMock).toHaveBeenCalledWith('agent.acp_backend', 'codex'))
  })

  it('hides a backend excluded by public policy', async () => {
    schemaMock.mockReturnValue(schemaWith(['codex']))
    mount()
    await screen.findByRole('button', { name: 'Codex CLI' })
    expect(screen.queryByRole('button', { name: 'OpenAI Compatible' })).not.toBeInTheDocument()
  })

  it('keeps a currently selected backend visible if policy changes underneath it', async () => {
    codexcrewConfigMock.mockResolvedValue({ agent: { acp_backend: 'openai_compatible' } })
    schemaMock.mockReturnValue(schemaWith(['codex']))
    mount()
    expect(await screen.findByRole('button', { name: 'OpenAI Compatible' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('offers a retry instead of inventing a selection when config loading fails', async () => {
    codexcrewConfigMock.mockRejectedValueOnce(new Error('offline'))
    mount()
    expect(await screen.findByText('Could not load the agent backend.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Codex CLI' })).not.toBeInTheDocument()
    codexcrewConfigMock.mockResolvedValue({ agent: { acp_backend: 'codex' } })
    fireEvent.click(button('Retry'))
    expect(await screen.findByRole('button', { name: 'Codex CLI' })).toBeEnabled()
  })

  it('disables a missing CLI and attaches its actionable reason', async () => {
    acpBackendsMock.mockResolvedValue({
      backends: PUBLIC.map(id => probeRow(id, id === 'codex' ? {
        installed: 'missing', missing_components: ['codex-acp'], install_command: 'install codex-acp',
      } : {})),
    })
    mount()
    await waitFor(() => expect(button('Codex CLI')).toBeDisabled())
    const describedBy = button('Codex CLI').getAttribute('aria-describedby')
    expect(document.getElementById(describedBy!)).toHaveTextContent('Missing on this machine: codex-acp. Install with: install codex-acp')
  })

  it('installs and hooks Codex in one click when only the bundled runtime is available', async () => {
    const before = PUBLIC.map(id => probeRow(id, id === 'codex' ? {
      codex_cli_source: 'bundled', codex_cli_version: '', one_click_install: true,
    } : {}))
    const after = PUBLIC.map(id => probeRow(id))
    acpBackendsMock.mockResolvedValue({ backends: before })
    installCodexMock.mockResolvedValue({
      ok: true,
      codex_cli: { version: '1.2.3', source: 'official' },
      adapter_ready: true,
      backends: after,
    })

    mount()
    expect(await screen.findByText('Using the bundled Codex runtime.')).toBeInTheDocument()
    fireEvent.click(button('Install and connect Codex'))

    await waitFor(() => expect(installCodexMock).toHaveBeenCalledOnce())
    expect(await screen.findByText('Using Codex CLI 1.2.3 from this machine.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Install and connect Codex' })).not.toBeInTheDocument()
  })

  it('keeps the one-click action available after an install failure', async () => {
    acpBackendsMock.mockResolvedValue({
      backends: PUBLIC.map(id => probeRow(id, id === 'codex' ? {
        codex_cli_source: 'bundled', codex_cli_version: '', one_click_install: true,
      } : {})),
    })
    installCodexMock.mockRejectedValue(new Error('offline'))

    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Install and connect Codex' }))

    expect(await screen.findByText('Could not install Codex CLI. Check the gateway log and try again.')).toBeInTheDocument()
    expect(button('Install and connect Codex')).toBeEnabled()
  })

  it('keeps an unknown install verdict enabled', async () => {
    acpBackendsMock.mockResolvedValue({ backends: [probeRow('openai_compatible', { installed: 'unknown' })] })
    mount()
    await waitFor(() => expect(screen.getByText('Could not check whether this is installed on this machine.')).toBeInTheDocument())
    expect(button('OpenAI Compatible')).toBeEnabled()
  })

  it('fails open when the machine probe endpoint is unavailable', async () => {
    acpBackendsMock.mockRejectedValue(new Error('403 Forbidden'))
    mount()
    await screen.findByRole('button', { name: 'Codex CLI' })
    for (const name of ['Codex CLI', 'OpenAI Compatible']) expect(button(name)).toBeEnabled()
  })

  it('renders a plugin backend under its server policy name', async () => {
    schemaMock.mockReturnValue(schemaWith([...PUBLIC, 'future-agent']))
    acpBackendsMock.mockResolvedValue({ backends: [probeRow('future-agent', { policy_id: 'Future Agent' })] })
    mount()
    expect(await screen.findByRole('button', { name: 'Future Agent' })).toBeEnabled()
    fireEvent.click(button('Future Agent'))
    await waitFor(() => expect(patchConfigMock).toHaveBeenCalledWith('agent.acp_backend', 'future-agent'))
  })

  it('marks Codex as the default and explains the two credential paths', async () => {
    mount()
    await screen.findByRole('button', { name: 'Codex CLI' })
    expect(screen.getByText('Default. All features supported.')).toBeInTheDocument()
    expect(screen.getByText(/encrypted API key configured in Settings/)).toBeInTheDocument()
    expect(screen.getByText(/Codex signs in on its own/)).toBeInTheDocument()
    expect(screen.getByText(/decided when the gateway starts/)).toBeInTheDocument()
  })

  it('surfaces a rejected save and keeps the confirmed selection', async () => {
    patchConfigMock.mockRejectedValueOnce(new Error('nope'))
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'OpenAI Compatible' }))
    expect(await screen.findByText('Could not save the agent backend.')).toBeInTheDocument()
    expect(button('Codex CLI')).toHaveAttribute('aria-pressed', 'true')
  })
})
