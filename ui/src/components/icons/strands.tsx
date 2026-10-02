// Strands Agents mark (https://strandsagents.com): two strands of a helix,
// traced from the project's logo as stroked paths. Unlike the other marks in
// this folder it keeps its own two colours rather than currentColor - the
// green strand is the brand.

interface IconProps {
  className?: string
  title?: string
}

export function StrandsLogo({ className, title }: IconProps) {
  return (
    <svg
      viewBox="0 0 178 284"
      fill="none"
      strokeWidth={28}
      strokeLinecap="round"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
    >
      <path
        stroke="#989898"
        d="M53 45.6L145.4 71A21.2 21.2 0 0 1 149.3 110.4L25.6 172.2A21.1 21.1 0 0 0 29 211.2L117.5 237.8"
      />
      <path
        stroke="#00F870"
        d="M163 12.6L39.3 49.7A35.5 35.5 0 0 0 33.9 115.5L144.5 169.7A33.1 33.1 0 0 1 139.6 231L15 269"
      />
    </svg>
  )
}
