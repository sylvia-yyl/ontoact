import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiClientV2, formatApiError } from '@/api/client'
import { requestId } from '@/lib/requestId'
import './decision-package.css'
import { describe, humanize, plain, useRunPackage, type DecisionPackage, type DecisionRunContext, type Delivery } from './decisionPackage'

const editLabel: Record<string, string> = { set_property: 'Set', create_object: 'Create', delete_object: 'Delete', unset_property: 'Clear' }
const eventLabel: Record<string, string> = { created: 'Created', begin_apply: 'Apply started', apply_succeeded: 'Applied', apply_failed: 'Apply failed', revert: 'Reverted', supersede: 'Superseded' }
const packageStatus: Record<string, string> = { draft: 'Draft', applying: 'Applying', applied: 'Applied', apply_failed: 'Apply failed', reverted: 'Reverted', superseded: 'Superseded' }

export default function DecisionPackagePanel({ context, candidate, actionLabel = {} }: { context?: DecisionRunContext; candidate: { id: string; applicable: boolean }; actionLabel?: Record<string, string> }) {
  const { pkg, setPkg, candidateId } = useRunPackage(context)
  const [rationale, setRationale] = useState('')
  const [delivery, setDelivery] = useState<Delivery | null>(null)
  const packagesUrl = `/ontologies/${context?.ontologyId}/decision-packages`
  // The server compiles the candidate into typed edits from the run's pinned data view.
  const createPackage = useMutation({
    mutationFn: () => apiClientV2.post<DecisionPackage>(`/ontologies/${context!.ontologyId}/scenario-study-runs/${context!.runId}/decision-packages`, { candidate_id: candidate.id, rationale: rationale.trim() }),
    onSuccess: setPkg,
  })
  // One request id per click; a retried request is answered from the recorded event.
  const command = useMutation({
    mutationFn: (verb: 'apply' | 'revert' | 'deliver-outbox') => apiClientV2.post<{ package: DecisionPackage; delivery?: Delivery }>(`${packagesUrl}/${pkg!.id}:${verb}`, verb === 'deliver-outbox' ? undefined : { expected_etag: pkg!.etag, request_id: requestId() }),
    onSuccess: result => { setPkg(result.package); if (result.delivery) setDelivery(result.delivery) },
  })
  const error = createPackage.error || command.error
  const edits = pkg?.actions.flatMap(action => action.expected_edits.filter(edit => edit.op !== 'invoke_action').map(edit => ({ action, edit }))) ?? []
  const label = (key: string) => actionLabel[key] ?? humanize(key)

  if (pkg && candidateId && candidateId !== candidate.id) return <>
    <p role="status" className="candidate-warning">This run already has an active decision package for another action. Select that action to review, apply, or revert it.</p>
    <p className="candidate-note">Only one active decision package is shown for a run, so controls for it are never displayed under a different action.</p>
  </>

  return <>
    {!pkg ? <>
      <label className="candidate-field">Rationale<textarea value={rationale} onChange={event => setRationale(event.target.value)} rows={3} placeholder="Why this option, and which trade-offs you accept" /></label>
      <button className="wb-button-primary mt-2" disabled={!candidate.applicable || !context || !rationale.trim() || createPackage.isPending} onClick={() => createPackage.mutate()}>Create decision package</button>
      {!context && <p className="candidate-note">A decision package can be created once the run has finished.</p>}
    </> : <div className="package-panel" data-testid="decision-package">
      <p><strong>{packageStatus[pkg.status] ?? pkg.status}</strong> · revision {pkg.etag}</p>
      <p className="candidate-note">Ontology changes ({edits.length}), recompiled and checked against the digest when applied:</p>
      <ol className="candidate-actions" data-testid="package-edits">{edits.map(({ action, edit }) => <li key={edit.sequence}><strong>{editLabel[edit.op] ?? edit.op} · {edit.target?.concrete_type} {plain(edit.target?.object_id ?? '')}</strong><small>{edit.property ? plain(`${edit.property}: ${String(edit.expected_old_value ?? 'empty')} → ${String(edit.value ?? 'empty')}`) : describe({ action_type: action.action_type_id, ...edit.properties })}</small></li>)}</ol>
      {(pkg.status === 'draft' || pkg.status === 'apply_failed') && <button className="wb-button-primary" disabled={command.isPending} onClick={() => command.mutate('apply')}>{pkg.status === 'apply_failed' ? 'Retry apply' : 'Apply to ontology'}</button>}
      {pkg.status === 'applied' && <>
        <ul className="package-receipts" data-testid="package-receipts">{pkg.actions.filter(action => action.external_effect_class !== 'none').map(action => <li key={action.id}>{label(action.action_type_id)} · {action.receipt ? `${String(action.receipt.connector_label ?? action.receipt.connector)} · receipt ${String(action.receipt.external_id)}` : 'Pending'}</li>)}</ul>
        {delivery?.status === 'external_effect_partial' && <p className="candidate-warning">Ontology changes are applied, but {delivery.external_effects - delivery.delivered} external notifications were not delivered.</p>}
        <div className="package-buttons">
          {pkg.outbox.some(row => !row.delivered) && <button className="wb-button-secondary" disabled={command.isPending} onClick={() => command.mutate('deliver-outbox')}>Resend notifications</button>}
          <button className="wb-button-secondary" disabled={command.isPending} onClick={() => command.mutate('revert')}>Revert ontology changes</button>
        </div>
      </>}
      {pkg.status === 'reverted' && pkg.actions.some(action => action.receipt) && <p className="candidate-warning">Ontology changes are reverted. Notifications already sent to external parties cannot be recalled; follow up with them directly.</p>}
      <ol className="package-events">{pkg.events.map(row => <li key={row.sequence}>{eventLabel[row.event_type] ?? humanize(row.event_type)} by {row.actor_name ?? 'another user'}{row.created_at ? ` · ${new Date(row.created_at).toLocaleString()}` : ''}{row.reason ? ` · ${row.reason}` : ''}</li>)}</ol>
    </div>}
    {error && <p role="alert" className="candidate-warning">{formatApiError(error)}</p>}
    <p className="candidate-note">Apply recompiles the changes and stops if the run's scenario has changed since the package was created.</p>
  </>
}
