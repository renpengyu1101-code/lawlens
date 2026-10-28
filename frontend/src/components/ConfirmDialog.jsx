import { useEffect, useRef } from 'react'

/**
 * 二次确认弹窗：毛玻璃遮罩 + 居中卡片，替代浏览器原生 confirm。
 * props: open / title / message / detail / confirmText / cancelText / danger / onConfirm / onCancel
 */
export default function ConfirmDialog({
  open,
  title = '确认操作',
  message = '',
  detail = '',
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  onConfirm,
  onCancel,
}) {
  const confirmRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    confirmRef.current?.focus()
    const onKey = (event) => {
      if (event.key === 'Escape') onCancel?.()
      if (event.key === 'Enter') onConfirm?.()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onCancel, onConfirm])

  if (!open) return null

  return (
    <div
      className="dlg-overlay"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel?.() }}
    >
      <div className="dlg-card" role="alertdialog" aria-modal="true" aria-label={title}>
        <h3 className="dlg-title">{title}</h3>
        {message && <p className="dlg-message">{message}</p>}
        {detail && <p className="dlg-detail">{detail}</p>}
        <div className="dlg-actions">
          <button className="btn ghost" onClick={() => onCancel?.()}>{cancelText}</button>
          <button
            ref={confirmRef}
            className={`btn ${danger ? 'danger' : 'primary'}`}
            onClick={() => onConfirm?.()}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
