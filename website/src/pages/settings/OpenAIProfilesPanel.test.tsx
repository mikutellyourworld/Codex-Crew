import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { OpenAIProfilesPanel } from './OpenAIProfilesPanel'

const profiles = {
  active: 'freechain',
  profiles: [
    {
      id: 'freechain',
      name: 'FreeChain',
      base_url: 'http://127.0.0.1:4853/v1',
      model: 'auto',
      builtin: true,
      key_configured: false,
      source_url: 'https://github.com/BarnsL/FreeChain-API',
    },
  ],
}

let calls: Array<{ url: string; method: string; body?: Record<string, unknown> }> = []
let backend = 'codex'

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <OpenAIProfilesPanel />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  calls = []
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ url, method, body })
    const responseBody = url === '/api/config/codexcrew'
      ? { agent: { acp_backend: backend } }
      : profiles
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(responseBody),
    } as Response)
  }))
})

afterEach(() => vi.unstubAllGlobals())

describe('OpenAIProfilesPanel', () => {
  it('shows FreeChain by BarnsL first with a dedicated masked API key field', async () => {
    mount()
    expect(await screen.findByText('FreeChain')).toBeInTheDocument()
    expect(screen.getByText('Built in, by BarnsL')).toBeInTheDocument()
    expect(screen.getByDisplayValue('http://127.0.0.1:4853/v1')).toBeDisabled()
    expect(screen.getByLabelText('FreeChain API key')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('link', { name: 'FreeChain source' })).toHaveAttribute(
      'href',
      'https://github.com/BarnsL/FreeChain-API',
    )
    expect(screen.getByText('Selected profile')).toBeInTheDocument()
    expect(screen.queryByText('Active')).not.toBeInTheDocument()
  })

  it('marks the selected profile active only when OpenAI-compatible is the runtime', async () => {
    backend = 'openai_compatible'
    mount()

    expect(await screen.findByText('Active')).toBeInTheDocument()
    expect(screen.queryByText('Selected profile')).not.toBeInTheDocument()
  })

  it('updates the built-in profile key without putting it in profile metadata', async () => {
    const user = userEvent.setup()
    mount()
    const input = await screen.findByLabelText('FreeChain API key')
    await user.type(input, 'local-test-key')
    await user.click(screen.getByRole('button', { name: 'Save FreeChain key' }))
    await waitFor(() => expect(calls).toContainEqual({
      url: '/api/openai-profiles',
      method: 'POST',
      body: { id: 'freechain', api_key: 'local-test-key', active: true },
    }))
  })

  it('offers fields for adding more than one OpenAI-compatible provider', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Add provider' }))
    expect(screen.getByLabelText('Provider name')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Base URL').some(input => !input.hasAttribute('disabled'))).toBe(true)
    expect(screen.getAllByLabelText('Model').some(input => !input.hasAttribute('disabled'))).toBe(true)
    expect(screen.getByLabelText('API key')).toHaveAttribute('type', 'password')
  })
})
