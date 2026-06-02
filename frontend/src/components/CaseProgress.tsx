import type { MriCase } from '../types/api'
import { getCaseCompletion, getCaseSteps } from '../utils/userFacing'

export function CaseProgress({ mriCase, compact = false }: { mriCase: MriCase; compact?: boolean }) {
  const steps = getCaseSteps(mriCase)
  const completion = getCaseCompletion(mriCase)

  return (
    <div className={compact ? 'case-progress compact-case-progress' : 'case-progress'}>
      <div className="progress-summary-row">
        <strong>{completion}% complete</strong>
        <span>{steps.filter((step) => step.complete).length} of {steps.length} steps ready</span>
      </div>
      <div className="progress-wrap" aria-label={`${completion}% complete`}>
        <div className="progress-bar" style={{ width: `${completion}%` }} />
      </div>
      <ol className="processing-steps">
        {steps.map((step) => (
          <li className={step.complete ? 'complete' : ''} key={step.key}>
            <span aria-hidden="true">{step.complete ? '✓' : '•'}</span>
            <div>
              <strong>{step.title}</strong>
              {!compact && <p>{step.description}</p>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
