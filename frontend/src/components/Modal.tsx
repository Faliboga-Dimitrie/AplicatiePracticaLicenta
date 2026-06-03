import type { ReactNode } from 'react'

type ModalProps = {
  title: string
  eyebrow?: string
  children: ReactNode
  footer?: ReactNode
  onClose: () => void
  hideCloseButton?: boolean
}

export function Modal({ title, eyebrow, children, footer, onClose, hideCloseButton = false }: ModalProps) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="row-between modal-header">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            <h2 id="modal-title">{title}</h2>
          </div>
          {!hideCloseButton && (
            <button type="button" className="secondary mini-button" onClick={onClose} aria-label="Close dialog">
              Close
            </button>
          )}
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="button-row modal-footer">{footer}</div>}
      </section>
    </div>
  )
}
