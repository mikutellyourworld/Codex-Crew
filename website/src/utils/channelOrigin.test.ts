import { describe, it, expect } from 'vitest'
import { slotChannelLabel, slotChannelNamespace } from './channelOrigin'

describe('slotChannelLabel', () => {
  it('labels every channel namespace', () => {
    expect(slotChannelLabel('slack:1785370133.085469')).toBe('Slack')
    expect(slotChannelLabel('discord:codexcrew:direct:U1')).toBe('Discord')
    expect(slotChannelLabel('telegram:codexcrew:direct:U1')).toBe('Telegram')
    expect(slotChannelLabel('whatsapp:codexcrew:direct:U1')).toBe('WhatsApp')
    expect(slotChannelLabel('webex:codexcrew:direct:U1')).toBe('Webex')
    expect(slotChannelLabel('wecom:codexcrew:direct:U1')).toBe('WeCom')
    expect(slotChannelLabel('teams:codexcrew:direct:U1')).toBe('Teams')
    expect(slotChannelLabel('weixin:codexcrew:direct:U1')).toBe('Weixin')
    expect(slotChannelLabel('unified:codexcrew')).toBe('Direct message')
  })

  it('labels the persisted filename-stem form too', () => {
    // list_sessions() reports the stem, where history._safe_key folded ':' -> '_'.
    expect(slotChannelLabel('slack_1785370133.085469')).toBe('Slack')
    expect(slotChannelLabel('discord_codexcrew_direct_U1')).toBe('Discord')
    expect(slotChannelLabel('unified_codexcrew')).toBe('Direct message')
  })

  it('returns empty for non-channel producers so no glyph renders', () => {
    expect(slotChannelLabel('cron:abc123')).toBe('')
    expect(slotChannelLabel('cron_abc123')).toBe('')
    expect(slotChannelLabel('hook:default:1')).toBe('')
    expect(slotChannelLabel('subagent:xyz')).toBe('')
    expect(slotChannelLabel('dashboard:chat-1-1')).toBe('')
    expect(slotChannelLabel('dashboard_chat-1-1')).toBe('')
    expect(slotChannelLabel('channel:general')).toBe('')
  })

  it('returns empty for an unlinked slot', () => {
    expect(slotChannelLabel(undefined)).toBe('')
    expect(slotChannelLabel('')).toBe('')
  })

  it('does not match a namespace by prefix alone', () => {
    expect(slotChannelLabel('slackish:1.2')).toBe('')
  })

  it('is case-sensitive so a user-titled session is not mislabelled', () => {
    // A title-derived slot name like "Slack thread triage" folds to
    // "Slack_thread_triage" — capital S, so it is NOT channel-origin.
    expect(slotChannelLabel('Slack_thread_triage')).toBe('')
    expect(slotChannelLabel('Teams_sync_notes')).toBe('')
  })
})

describe('slotChannelNamespace', () => {
  it('returns the namespace for both key separators', () => {
    expect(slotChannelNamespace('slack:1785370133.085469')).toBe('slack')
    expect(slotChannelNamespace('slack_1785370133.085469')).toBe('slack')
    expect(slotChannelNamespace('1785370133.085469')).toBe('slack')
    expect(slotChannelNamespace('discord:bot:direct:u1')).toBe('discord')
  })

  it('singles out unified, which has no proper-noun label to interpolate', () => {
    // The tooltip routes this namespace to its own locale key so a translated
    // sentence never has to embed the English article form.
    expect(slotChannelNamespace('unified:codexcrew')).toBe('unified')
    expect(slotChannelNamespace('unified_codexcrew')).toBe('unified')
  })

  it('returns empty for dashboard sessions and non-channel keys', () => {
    expect(slotChannelNamespace('dashboard:chat-1-1')).toBe('')
    expect(slotChannelNamespace('slackish:1.2')).toBe('')
    expect(slotChannelNamespace('Slack_thread_triage')).toBe('')
    expect(slotChannelNamespace(undefined)).toBe('')
    expect(slotChannelNamespace('')).toBe('')
  })

  it('agrees with slotChannelLabel on what counts as channel-origin', () => {
    for (const key of ['slack:1.1', 'unified_codexcrew', 'dashboard:chat-1', 'Slack_x', '']) {
      expect(Boolean(slotChannelNamespace(key))).toBe(Boolean(slotChannelLabel(key)))
    }
  })
})

describe('isChatPageSurface — member exclusion', () => {
  it('never admits member DM threads into chat-page surfaces', async () => {
    // This predicate is the ONE gate keeping member-<slug> threads out of the
    // Sessions sidebar and the resume paths — the Crew Members page is their
    // only home. Adding 'member' to the admit set silently leaks every DM
    // thread into Sessions; this pin is what makes that change visible.
    const { isChatPageSurface } = await import('./channelOrigin')
    expect(isChatPageSurface('member')).toBe(false)
    // The admitted set, pinned exactly: growing it is a deliberate act.
    expect(isChatPageSurface('')).toBe(true)
    expect(isChatPageSurface(undefined)).toBe(true)
    expect(isChatPageSurface('orchestrator')).toBe(true)
    expect(isChatPageSurface('crew')).toBe(true)
  })
})
