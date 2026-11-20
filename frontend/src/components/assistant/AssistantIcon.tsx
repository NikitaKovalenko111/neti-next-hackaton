const iconPaths = {
  book: 'M4 19V5a2 2 0 0 1 2-2h14v18H6a2 2 0 0 1 0-4h14M8 7h8M8 11h5',
  blocks: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM17 14v6M14 17h6',
  cap: 'M2 9l10-5 10 5-10 5L2 9zm4 2v5c3 3 9 3 12 0v-5m4-2v6',
  chat: 'M20.5 11.5a7.5 7.5 0 0 1-7.5 7.5H9l-4.5 2v-5A7.5 7.5 0 0 1 10 4h3a7.5 7.5 0 0 1 7.5 7.5zM9 10h7m-7 4h4',
  globe: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0zM2 12h20M12 2c5 5 5 15 0 20-5-5-5-15 0-20z',
  home: 'M3 10l9-7 9 7M5 9v12h14V9M9 21v-7h6v7',
  link: 'M10 13a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1.5 1.5M14 11a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1.5-1.5',
  moon: 'M20.9 13.35A9 9 0 0 1 10.65 3.1a9 9 0 1 0 10.25 10.25z',
  plus: 'M12 5v14M5 12h14',
  send: 'M22 2l-7 20-4-9-9-4 20-7zM22 2L11 13',
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
  return <span className="assistant-mark" aria-hidden="true"><span /></span>
}
