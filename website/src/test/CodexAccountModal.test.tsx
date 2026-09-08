import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { acpBackendsMock, codexcrewConfigMock, patchConfigMock, schemaMock } = vi.hoisted(() => ({
  acpBackendsMock: vi.fn(),
  codexcrewConfigMock: vi.fn(),
  patchConfigMock: vi.fn(),
  schemaMock: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    acpBackends: acpBackendsMock,
    codexcrewConfig: codexcrewConfigMock,
    patchConfig: patchConfigMock,
  },
}))

vi.mock('../components/settingRef/useConfigSchema', () => ({
  useConfigSchema: () => schemaMock(),
}))

import type { AcpBackendProbe } from '../api/client'
import CodexAccountModal from '../components/CodexAccountModal'
import { renderWithProviders } from './helpers'

const INSTALLED: AcpBackendProbe = {
  id: 'codex',
  policy_id: 'codex',
  selectable: true,
  installed: 'installed',
  missing_components: [],
  install_command: '',
  restart_required: false,
}

const PUBLIC = ['codex', 'openai_compatible']

beforeEach(() => {
  acpBackendsMock.mockReset().mockResolvedValue({
    backends: PUBLIC.map(id => ({
      ...INSTALLED,
      id,
      policy_id: id,
    })),
  })
  codexcrewConfigMock.mockReset().mockResolvedValue({ agent: { acp_backend: 'codex' } })
  patchConfigMock.mockReset().mockResolvedValue({})
  schemaMock.mockReset().mockReturnValue(new Map([
    ['agent.acp_backend', { path: 'agent.acp_backend', type: 'enum', enum: PUBLIC }],
  ]))
})

describe('CodexAccountModal', () => {
  it('presents Codex CLI as the primary ready backend', async () => {
    renderWithProviders(<CodexAccountModal open onClose={vi.fn()} status={INSTALLED} />)

    expect(await screen.findByRole('dialog', { name: 'Codex CLI' })).toBeInTheDocument()
    expect(screen.getByText('Ready on this machine')).toBeInTheDocument()
    expect(screen.getByText('Primary agent backend')).toBeInTheDocument()
    expect(screen.getByText('Installed')).toBeInTheDocument()
    expect(screen.getByText(/codex login/)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Codex CLI' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'OpenAI Compatible' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Claude Code' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Kimi CLI' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Codex CLI' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('link', { name: 'Codex CLI documentation' })).toHaveAttribute(
      'href',
      'https://developers.openai.com/codex/cli/',
    )
  })

  it('shows actionable missing components instead of account or credit errors', async () => {
    renderWithProviders(
      <CodexAccountModal
        open
        onClose={vi.fn()}
        status={{
          ...INSTALLED,
          installed: 'missing',
          missing_components: ['codex-acp'],
          install_command: 'npm install -g @agentclientprotocol/codex-acp',
        }}
      />,
    )

    expect(await screen.findByText('Codex CLI needs setup')).toBeInTheDocument()
    expect(screen.getByText('codex-acp')).toBeInTheDocument()
    expect(screen.getByText('npm install -g @agentclientprotocol/codex-acp')).toBeInTheDocument()
    expect(screen.queryByText(/credit usage/i)).not.toBeInTheDocument()
  })

  it('shows a bounded loading state and closes accessibly', async () => {
    acpBackendsMock.mockReturnValue(new Promise(() => {}))
    const onClose = vi.fn()
    renderWithProviders(<CodexAccountModal open onClose={onClose} />)

    expect(await screen.findByText('Checking Codex CLI…')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('switches the runtime for new sessions through the shared backend control', async () => {
    renderWithProviders(<CodexAccountModal open onClose={vi.fn()} status={INSTALLED} />)

    fireEvent.click(await screen.findByRole('button', { name: 'OpenAI Compatible' }))
    await waitFor(() => {
      expect(patchConfigMock).toHaveBeenCalledWith('agent.acp_backend', 'openai_compatible')
    })
  })

  it('keeps Codex primary while truthfully showing another selected runtime', async () => {
    codexcrewConfigMock.mockResolvedValue({ agent: { acp_backend: 'openai_compatible' } })
    renderWithProviders(<CodexAccountModal open onClose={vi.fn()} status={INSTALLED} />)

    expect(await screen.findByText('Primary agent backend')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'OpenAI Compatible' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Codex CLI' })).toHaveAttribute('aria-pressed', 'false')
  })
})
