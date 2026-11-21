import { UniversityMark } from '../project-header/UniversityMark'

const iconPaths = {
  book: 'M12 6c-3-2.5-6.5-3-10-2v15c3.5-1 7-.5 10 2 3-2.5 6.5-3 10-2V4c-3.5-1-7-.5-10 2zm0 0v15',
  cap: 'M2 9l10-5 10 5-10 5L2 9zm4 2v5c3 3 9 3 12 0v-5m4-2v6',
  link: 'M10 13a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1.5 1.5M14 11a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1.5-1.5',
  moon: 'M20.9 13.35A9 9 0 0 1 10.65 3.1a9 9 0 1 0 10.25 10.25z',
  pin: 'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0zm-5 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  plus: 'M12 5v14M5 12h14',
  sun: 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0-14v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42',
}

export function AssistantIcon({ name }: { name: keyof typeof iconPaths }) {
  return (
    <svg
      aria-hidden="true"
      className="assistant-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={iconPaths[name]} />
    </svg>
  )
}

export function AssistantMark() {
  return <span className="assistant-mark" aria-hidden="true"><UniversityMark className="assistant-symbol" /></span>
}
