import type { SVGProps } from 'react'

type AgentHopMascotProps = SVGProps<SVGSVGElement>

/** A friendly courier companion for the AgentHop hero. */
export function AgentHopMascot({
  'aria-label': ariaLabel = 'AgentHop mascot',
  ...props
}: AgentHopMascotProps) {
  return (
    <svg
      viewBox="0 0 220 180"
      width="220"
      height="180"
      role="img"
      aria-label={ariaLabel}
      {...props}
    >
      <path d="M28 108c0-44 31-82 80-82 42 0 76 26 84 65 5 26-12 51-39 55-31 5-48-20-75-9-29 12-50 1-50-29Z" fill="#dfead5" />
      <path d="M145 52c18 5 31 20 34 39" fill="none" stroke="#c7ed70" strokeWidth="12" strokeLinecap="round" />
      <path d="M50 96c0-27 19-49 46-49 23 0 43 15 48 36l8 34c4 18-10 35-29 35H77c-18 0-32-15-29-33l2-23Z" fill="#1f7655" />
      <path d="M63 92c0-19 14-34 33-34s34 15 34 34v25c0 18-15 32-34 32s-33-14-33-32V92Z" fill="#fbfaf6" />
      <path d="M70 79c8-18 23-28 40-28 13 0 25 6 33 17-13-2-22 3-29 11-15-7-29-6-44 0Z" fill="#f1a15a" />
      <path d="M80 103h1m29 0h1" fill="none" stroke="#1c2420" strokeWidth="7" strokeLinecap="round" />
      <path d="M88 120c5 5 12 5 17 0" fill="none" stroke="#1f7655" strokeWidth="4" strokeLinecap="round" />
      <path d="M46 119 28 134m105-13 20 12" fill="none" stroke="#1f7655" strokeWidth="11" strokeLinecap="round" />
      <path d="M78 142 70 160m42-18 11 16" fill="none" stroke="#1f7655" strokeWidth="11" strokeLinecap="round" />
      <path d="M61 163c6-4 13-4 19 0m34 0c6-4 13-4 19 0" fill="none" stroke="#1c2420" strokeWidth="6" strokeLinecap="round" />
      <path d="M53 82 31 87m18 12-28 7m132-8 27-11" fill="none" stroke="#f1a15a" strokeWidth="6" strokeLinecap="round" />
      <path d="m154 116 8 8 18-21" fill="none" stroke="#c7ed70" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M41 171h126" stroke="#1c2420" strokeWidth="5" strokeLinecap="round" opacity=".16" />
    </svg>
  )
}
