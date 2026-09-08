import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ExternalLink, KeyRound, Plus, Trash2 } from 'lucide-react'

import { api, type OpenAICompatibleProfile } from '../../api/client'
import ErrorNotice from '../../components/ErrorNotice'
import { SettingsCard, SettingsSection } from '../../components/settings'
import { Btn } from '../../components/ui'
import { i18nT } from '../../i18n/t'

const QUERY_KEY = ['openAICompatibleProfiles'] as const

function slug(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

export function OpenAIProfilesPanel() {
  const qc = useQueryClient()
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [showAdd, setShowAdd] = useState(false)
  const [draft, setDraft] = useState({ name: '', base_url: '', model: 'auto', api_key: '' })

  const profilesQ = useQuery({ queryKey: QUERY_KEY, queryFn: api.openAIProfiles })
  const backendQ = useQuery<{ agent?: { acp_backend?: string } }>({
    queryKey: ['codexcrewConfig'],
    queryFn: () => api.codexcrewConfig(),
  })
  const refresh = () => qc.invalidateQueries({ queryKey: QUERY_KEY })

  const saveMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.saveOpenAIProfile(body),
    onSuccess: (_data, body) => {
      const id = String(body.id ?? '')
      setKeys(current => ({ ...current, [id]: '' }))
      setShowAdd(false)
      setDraft({ name: '', base_url: '', model: 'auto', api_key: '' })
      refresh()
    },
  })
  const selectMut = useMutation({ mutationFn: api.selectOpenAIProfile, onSuccess: refresh })
  const deleteMut = useMutation({ mutationFn: api.deleteOpenAIProfile, onSuccess: refresh })

  const data = profilesQ.data
  const profiles = data?.profiles ?? []
  const runtimeUsesOpenAICompatible = backendQ.data?.agent?.acp_backend === 'openai_compatible'
  const busy = saveMut.isPending || selectMut.isPending || deleteMut.isPending
  const mutationError = saveMut.error || selectMut.error || deleteMut.error

  const saveKey = (profile: OpenAICompatibleProfile) => {
    const apiKey = keys[profile.id] ?? ''
    if (!apiKey) return
    saveMut.mutate({
      id: profile.id,
      ...(profile.builtin
        ? {}
        : { name: profile.name, base_url: profile.base_url, model: profile.model }),
      api_key: apiKey,
      active: true,
    })
  }

  const addProvider = () => {
    const id = slug(draft.name)
    if (!id || !draft.base_url.trim() || !draft.api_key) return
    saveMut.mutate({
      id,
      name: draft.name.trim(),
      base_url: draft.base_url.trim(),
      model: draft.model.trim() || 'auto',
      api_key: draft.api_key,
      active: true,
    })
  }

  return (
    <SettingsSection title={i18nT('settings.openai_profiles.title')}>
      <SettingsCard>
        <p className="text-sm text-muted mb-4">{i18nT('settings.openai_profiles.description')}</p>
        {profilesQ.isLoading && <p className="text-sm text-muted">{i18nT('settings.openai_profiles.loading')}</p>}
        {profilesQ.isError && (
          <ErrorNotice
            className="mb-4"
            message={i18nT('settings.openai_profiles.load_error', { error: (profilesQ.error as Error).message })}
            askAgent={!showAdd}
          />
        )}
        {mutationError && (
          <ErrorNotice
            className="mb-4"
            message={i18nT('settings.openai_profiles.save_error', { error: (mutationError as Error).message })}
          />
        )}

        <div className="space-y-3">
          {profiles.map(profile => {
            const selected = data?.active === profile.id
            const active = selected && runtimeUsesOpenAICompatible
            return (
              <div key={profile.id} className="rounded-lg border border-border bg-bg-elevated p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-text-strong">{profile.name}</span>
                      {active && (
                        <span className="inline-flex items-center gap-1 rounded bg-accent/15 px-1.5 py-0.5 text-[11px] text-accent">
                          <Check size={11} /> {i18nT('settings.openai_profiles.active')}
                        </span>
                      )}
                      {selected && !active && (
                        <span className="inline-flex items-center gap-1 rounded bg-accent/15 px-1.5 py-0.5 text-[11px] text-accent">
                          <Check size={11} /> {i18nT('settings.openai_profiles.selected_profile')}
                        </span>
                      )}
                    </div>
                    {profile.builtin && <p className="mt-0.5 text-xs text-muted">{i18nT('settings.openai_profiles.freechain_by_barnsl')}</p>}
                  </div>
                  <div className="flex gap-2">
                    {!selected && <Btn disabled={busy} onClick={() => selectMut.mutate(profile.id)}>{i18nT('settings.openai_profiles.use_provider')}</Btn>}
                    {!profile.builtin && (
                      <Btn
                        danger
                        disabled={busy}
                        onClick={() => deleteMut.mutate(profile.id)}
                        aria-label={i18nT('settings.openai_profiles.delete_provider_aria', { name: profile.name })}
                      >
                        <Trash2 size={14} />
                      </Btn>
                    )}
                  </div>
                </div>

                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  <label className="text-xs font-medium text-muted">
                    {i18nT('settings.openai_profiles.base_url')}
                    <input
                      className="mt-1 w-full rounded border border-border bg-bg px-2 py-1.5 text-sm text-text"
                      value={profile.base_url}
                      aria-label={i18nT('settings.openai_profiles.base_url')}
                      disabled
                      readOnly
                    />
                  </label>
                  <label className="text-xs font-medium text-muted">
                    {i18nT('settings.openai_profiles.model')}
                    <input
                      className="mt-1 w-full rounded border border-border bg-bg px-2 py-1.5 text-sm text-text"
                      value={profile.model}
                      aria-label={i18nT('settings.openai_profiles.model')}
                      disabled
                      readOnly
                    />
                  </label>
                </div>

                <div className="mt-2 flex flex-col gap-2 md:flex-row md:items-end">
                  <label className="min-w-0 flex-1 text-xs font-medium text-muted">
                    {profile.name} {i18nT('settings.openai_profiles.api_key')}
                    <span className="relative mt-1 flex">
                      <KeyRound size={14} className="pointer-events-none absolute left-2 top-2.5 text-muted" />
                      <input
                        type="password"
                        value={keys[profile.id] ?? ''}
                        onChange={event => setKeys(current => ({ ...current, [profile.id]: event.target.value }))}
                        placeholder={profile.key_configured ? '••••••••' : 'sk-...'}
                        aria-label={i18nT('settings.openai_profiles.api_key_aria', { name: profile.name })}
                        className="w-full rounded border border-border bg-bg py-1.5 pl-8 pr-2 text-sm text-text"
                      />
                    </span>
                  </label>
                  <Btn primary disabled={busy || !(keys[profile.id] ?? '')} onClick={() => saveKey(profile)}>
                    {i18nT('settings.openai_profiles.save_key', { name: profile.name })}
                  </Btn>
                </div>

                {profile.source_url && (
                  <a
                    href={profile.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-xs text-accent hover:underline"
                    aria-label={i18nT('settings.openai_profiles.source_aria', { name: profile.name })}
                  >
                    {i18nT('settings.openai_profiles.source')} <ExternalLink size={11} />
                  </a>
                )}
              </div>
            )
          })}
        </div>

        {showAdd ? (
          <div className="mt-3 space-y-3 rounded-lg border border-border p-3">
            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-xs font-medium text-muted">
                {i18nT('settings.openai_profiles.provider_name')}
                <input
                  className="mt-1 w-full rounded border border-border bg-bg px-2 py-1.5 text-sm text-text"
                  value={draft.name}
                  aria-label={i18nT('settings.openai_profiles.provider_name')}
                  onChange={e => setDraft(current => ({ ...current, name: e.target.value }))}
                />
              </label>
              <label className="text-xs font-medium text-muted">
                {i18nT('settings.openai_profiles.base_url')}
                <input
                  className="mt-1 w-full rounded border border-border bg-bg px-2 py-1.5 text-sm text-text"
                  value={draft.base_url}
                  aria-label={i18nT('settings.openai_profiles.base_url')}
                  onChange={e => setDraft(current => ({ ...current, base_url: e.target.value }))}
                  placeholder="https://api.example.com/v1"
                />
              </label>
              <label className="text-xs font-medium text-muted">
                {i18nT('settings.openai_profiles.model')}
                <input
                  className="mt-1 w-full rounded border border-border bg-bg px-2 py-1.5 text-sm text-text"
                  value={draft.model}
                  aria-label={i18nT('settings.openai_profiles.model')}
                  onChange={e => setDraft(current => ({ ...current, model: e.target.value }))}
                />
              </label>
              <label className="text-xs font-medium text-muted">
                {i18nT('settings.openai_profiles.api_key')}
                <input
                  type="password"
                  className="mt-1 w-full rounded border border-border bg-bg px-2 py-1.5 text-sm text-text"
                  value={draft.api_key}
                  aria-label={i18nT('settings.openai_profiles.api_key')}
                  onChange={e => setDraft(current => ({ ...current, api_key: e.target.value }))}
                  placeholder="sk-..."
                />
              </label>
            </div>
            <div className="flex gap-2">
              <Btn primary disabled={busy || !draft.name.trim() || !draft.base_url.trim() || !draft.api_key} onClick={addProvider}>{i18nT('settings.openai_profiles.save_provider')}</Btn>
              <Btn disabled={busy} onClick={() => setShowAdd(false)}>{i18nT('settings.secrets.cancel')}</Btn>
            </div>
          </div>
        ) : (
          <Btn className="mt-3" onClick={() => setShowAdd(true)}>
            <Plus size={14} className="mr-1" /> {i18nT('settings.openai_profiles.add_provider')}
          </Btn>
        )}
      </SettingsCard>
    </SettingsSection>
  )
}
