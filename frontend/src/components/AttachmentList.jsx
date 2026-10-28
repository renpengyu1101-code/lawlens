export default function AttachmentList({ files, progress = null, onRemove, disabled = false }) {
  if (!files.length) return null
  const phase = progress?.phase || 'selected'
  const percent = progress?.percent
  const status = {
    selected: '待上传 · 点击“开始核查”后上传',
    creating: '正在建立项目，附件等待上传…',
    uploading: percent == null ? '正在上传…' : `正在上传 ${percent}%`,
    processing: '传输完成，正在处理文件…',
    done: '上传完成',
    error: '上传未完成，请查看错误提示',
  }[phase]
  return (
    <section className="attachment-list" aria-label="附件列表" aria-busy={['creating', 'uploading', 'processing'].includes(phase)}>
      <div className="attachment-summary">
        <strong>附件（{files.length}）</strong>
        <span role="status" className={phase === 'error' ? 'attachment-error' : 'muted'}>{status}</span>
      </div>
      <ul>
        {files.map((file, i) => (
          <li key={`${file.name}-${i}`}>
            <span className="attachment-name">{file.name}</span>
            <span className="muted small">{file.size.toLocaleString()} 字节</span>
            {onRemove && <button type="button" className="btn ghost sm" disabled={disabled}
              onClick={() => onRemove(i)} aria-label={`移除 ${file.name}`}>移除</button>}
          </li>
        ))}
      </ul>
      {phase === 'uploading' && <progress aria-label="附件总上传进度" max="100" value={percent ?? undefined} />}
      {phase === 'processing' && <progress aria-label="正在处理附件" />}
    </section>
  )
}
