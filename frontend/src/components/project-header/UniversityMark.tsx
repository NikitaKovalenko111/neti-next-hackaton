export function UniversityMark({ className }: { className: string }) {
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 100 92" fill="currentColor">
      <use href={`${import.meta.env.BASE_URL}favicon.svg#uust-mark`} />
    </svg>
  )
}
