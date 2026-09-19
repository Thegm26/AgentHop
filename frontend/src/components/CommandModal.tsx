import { useEffect, useId, useRef, useState } from 'react'
import { CheckIcon, CloseIcon, CopyIcon, TerminalIcon } from './Icons'

interface Props {
  command: string
  title: string
  onClose: () => void
}

export function CommandModal({ command, title, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const resetTimer = useRef<number>()
  const titleId = useId()
  const descriptionId = useId()
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')

  useEffect(() => {
    const node = dialog.current
    if (!node) return
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (typeof node.showModal === 'function') node.showModal()
    else node.setAttribute('open', '')
    node.querySelector<HTMLElement>('[data-initial-focus]')?.focus()
    return () => {
      if (resetTimer.current) window.clearTimeout(resetTimer.current)
      if (typeof node.close === 'function') node.close()
      else node.removeAttribute('open')
      previouslyFocused?.focus()
    }
  }, [])

  async function copy() {
    const legacyCopy = () => {
      const textarea = document.createElement('textarea')
      textarea.value = command
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      try {
        textarea.select()
        return typeof document.execCommand === 'function' && document.execCommand('copy')
      } finally {
        textarea.remove()
      }
    }

    try {
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(command)
        } catch {
          if (!legacyCopy()) throw new Error('Copy is unavailable')
        }
      } else if (!legacyCopy()) {
        throw new Error('Copy is unavailable')
      }
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
    if (resetTimer.current) window.clearTimeout(resetTimer.current)
    resetTimer.current = window.setTimeout(() => setCopyState('idle'), 1800)
  }

  return (
    <dialog ref={dialog} className="command-dialog" aria-labelledby={titleId} aria-describedby={descriptionId} onCancel={(event) => { event.preventDefault(); onClose() }} onClick={(event) => { if (event.target === dialog.current) onClose() }}>
      <div className="dialog-card">
        <button className="icon-button dialog-close" data-initial-focus onClick={onClose} aria-label="Close command dialog"><CloseIcon /></button>
        <div className="dialog-icon"><TerminalIcon /></div>
        <p className="eyebrow">Ready to hop</p>
        <h2 id={titleId}>{title}</h2>
        <p className="dialog-copy" id={descriptionId}>Run this in your terminal. AgentHop has already selected the right account and session.</p>
        <div className="command-box">
          <code tabIndex={0} aria-label="Terminal command">{command}</code>
          <button className="copy-button" onClick={copy} aria-label="Copy command">
            {copyState === 'copied' ? <><CheckIcon /> Copied</> : copyState === 'failed' ? 'Select command' : <><CopyIcon /> Copy</>}
          </button>
          <span className="sr-only" aria-live="polite">{copyState === 'copied' ? 'Command copied to clipboard' : copyState === 'failed' ? 'Copy failed. Select the command manually.' : ''}</span>
        </div>
      </div>
    </dialog>
  )
}
