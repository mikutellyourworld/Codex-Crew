import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import DashboardBootstrap from '../components/DashboardBootstrap'

const { refreshScheduler } = vi.hoisted(() => ({
  refreshScheduler: vi.fn(),
}))

vi.mock('../hooks/useRefreshScheduler', () => ({
  useRefreshScheduler: () => refreshScheduler(),
}))

describe('DashboardBootstrap', () => {
  it('mounts auth recovery and does not block the app on kiro-cli', () => {
    render(<DashboardBootstrap><div>App</div></DashboardBootstrap>)

    expect(screen.getByText('App')).toBeInTheDocument()
    expect(refreshScheduler).toHaveBeenCalledOnce()
  })
})
