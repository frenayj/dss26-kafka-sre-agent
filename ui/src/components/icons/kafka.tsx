// Apache Kafka mark as a React component. Uses currentColor so it inherits
// the surrounding text color, matching the Lenses logo in ./lenses.tsx.
//
// Drawn as five rings joined by bars, measured from the Kafka logo the demo
// uses (the bold variant, not the thin-spoked original).

interface IconProps {
  className?: string
  title?: string
}

export function KafkaLogo({ className, title }: IconProps) {
  return (
    <svg
      viewBox="0 0 369 599"
      fill="none"
      stroke="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
    >
      <g strokeWidth={39.5}>
        <circle cx="100.4" cy="77.7" r="58.6" />
        <circle cx="100.4" cy="520.8" r="58.6" />
        <circle cx="290.4" cy="186.7" r="58.6" />
        <circle cx="290.4" cy="409.6" r="58.6" />
      </g>
      <circle cx="100.4" cy="297.8" r="77.6" strokeWidth={47.5} />
      <path
        strokeWidth={34}
        d="M100.4 136.3V220.2M100.4 375.4V462.2M169.2 262L238.3 213.6M169 334L238.1 383.1"
      />
    </svg>
  )
}
