import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

const base = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }

export const RefreshIcon = (props: IconProps) => <svg {...base} {...props}><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 9A7 7 0 0 1 18 6l2 2M18 15a7 7 0 0 1-11.9 3L4 16"/></svg>
export const ArrowIcon = (props: IconProps) => <svg {...base} {...props}><path d="M5 12h14M14 7l5 5-5 5"/></svg>
export const TerminalIcon = (props: IconProps) => <svg {...base} {...props}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>
export const CopyIcon = (props: IconProps) => <svg {...base} {...props}><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>
export const CheckIcon = (props: IconProps) => <svg {...base} {...props}><path d="m5 12 4 4L19 6"/></svg>
export const ClockIcon = (props: IconProps) => <svg {...base} {...props}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
export const SparkIcon = (props: IconProps) => <svg {...base} {...props}><path d="m12 3 1.4 4.1a5.5 5.5 0 0 0 3.5 3.5L21 12l-4.1 1.4a5.5 5.5 0 0 0-3.5 3.5L12 21l-1.4-4.1a5.5 5.5 0 0 0-3.5-3.5L3 12l4.1-1.4a5.5 5.5 0 0 0 3.5-3.5L12 3Z"/></svg>
export const CloseIcon = (props: IconProps) => <svg {...base} {...props}><path d="m6 6 12 12M18 6 6 18"/></svg>
