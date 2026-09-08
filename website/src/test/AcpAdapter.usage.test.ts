import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({
  api: {
    kiroUsage: vi.fn(),
  },
}))

import { api } from '../api/client'
import { AcpAdapter } from '../providers/adapters/acp'

const kiroUsage = api.kiroUsage as unknown as ReturnType<typeof vi.fn>

describe('AcpAdapter.fetchUsage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('normalizes missing Kiro session statistics to zero', async () => {
    kiroUsage.mockResolvedValue({ sessions: {}, billing: {} })

    await expect(new AcpAdapter().fetchUsage()).resolves.toEqual({
      sessions: {
        total: 0,
        today: { sessions: 0, messages: 0, toolCalls: 0 },
        thisWeek: { sessions: 0, messages: 0, toolCalls: 0 },
        thisMonth: { sessions: 0, messages: 0, toolCalls: 0 },
        avgMsgsPerSession: 0,
        dailyHistory: [],
      },
      billing: null,
    })
  })
})
