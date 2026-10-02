// Third-party service marks for the MCP servers the sub-agents drive, as
// React components matching the conventions of ./lenses.tsx and ./kafka.tsx.
// Single-colour marks use `currentColor`; pair them with the --brand-* tokens
// in src/index.css. Slack's mark is defined by its four colours, so it keeps
// them.
//
// Sources: GitHub Octicons mark-github; Atlassian Confluence 2017 logo (icon
// only); Slack 2019 icon; PagerDuty "P" traced from the 280px brand tile.

interface IconProps {
  className?: string
  title?: string
}

export function PagerDutyLogo({ className, title }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      fillRule="evenodd"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
    >
      <path d="M4.16 0.58H12.94A6.9 6.9 0 0 1 12.94 14.38H4.16ZM7.48 3.52V11.5H12.42A3.99 3.99 0 0 0 12.42 3.52ZM4.16 17.25H7.48V23.41H4.16Z" />
    </svg>
  )
}

export function GitHubLogo({ className, title }: IconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M8 0C3.58 0 0 3.58 0 8C0 11.54 2.29 14.53 5.47 15.59C5.87 15.66 6.02 15.42 6.02 15.21C6.02 15.02 6.01 14.39 6.01 13.72C4 14.09 3.48 13.23 3.32 12.78C3.23 12.55 2.84 11.84 2.5 11.65C2.22 11.5 1.82 11.13 2.49 11.12C3.12 11.11 3.57 11.7 3.72 11.94C4.44 13.15 5.59 12.81 6.05 12.6C6.12 12.08 6.33 11.73 6.56 11.53C4.78 11.33 2.92 10.64 2.92 7.58C2.92 6.71 3.23 5.99 3.74 5.43C3.66 5.23 3.38 4.41 3.82 3.31C3.82 3.31 4.49 3.1 6.02 4.13C6.66 3.95 7.34 3.86 8.02 3.86C8.7 3.86 9.38 3.95 10.02 4.13C11.55 3.09 12.22 3.31 12.22 3.31C12.66 4.41 12.38 5.23 12.3 5.43C12.81 5.99 13.12 6.7 13.12 7.58C13.12 10.65 11.25 11.33 9.47 11.53C9.76 11.78 10.01 12.26 10.01 13.01C10.01 14.08 10 14.94 10 15.21C10 15.42 10.15 15.67 10.55 15.59C13.71 14.53 16 11.53 16 8C16 3.58 12.42 0 8 0Z"
      />
    </svg>
  )
}

export function ConfluenceLogo({ className, title }: IconProps) {
  return (
    <svg
      viewBox="0 0 63.79 63.83"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
    >
      <path d="M2.23,49.53c-.65,1.06-1.38,2.29-2,3.27a2,2,0,0,0,.67,2.72l13,8a2,2,0,0,0,2.77-.68c.52-.87,1.19-2,1.92-3.21,5.15-8.5,10.33-7.46,19.67-3l12.89,6.13a2,2,0,0,0,2.69-1l6.19-14a2,2,0,0,0-1-2.62c-2.72-1.28-8.13-3.83-13-6.18C28.51,30.45,13.62,31,2.23,49.53Z" />
      <path d="M60.52,17.76c.65-1.06,1.38-2.29,2-3.27a2,2,0,0,0-.67-2.72l-13-8A2,2,0,0,0,46,4.43c-.52.87-1.19,2-1.92,3.21-5.15,8.5-10.33,7.46-19.67,3L11.56,4.54a2,2,0,0,0-2.69,1l-6.19,14a2,2,0,0,0,1,2.62c2.72,1.28,8.13,3.83,13,6.18C34.24,36.84,49.13,36.27,60.52,17.76Z" />
    </svg>
  )
}

export function SlackLogo({ className, title }: IconProps) {
  return (
    <svg
      viewBox="0 0 127 127"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
    >
      <path
        d="M27.2 80c0 7.3-5.9 13.2-13.2 13.2C6.7 93.2.8 87.3.8 80c0-7.3 5.9-13.2 13.2-13.2h13.2V80zm6.6 0c0-7.3 5.9-13.2 13.2-13.2 7.3 0 13.2 5.9 13.2 13.2v33c0 7.3-5.9 13.2-13.2 13.2-7.3 0-13.2-5.9-13.2-13.2V80z"
        fill="#E01E5A"
      />
      <path
        d="M47 27c-7.3 0-13.2-5.9-13.2-13.2C33.8 6.5 39.7.6 47 .6c7.3 0 13.2 5.9 13.2 13.2V27H47zm0 6.7c7.3 0 13.2 5.9 13.2 13.2 0 7.3-5.9 13.2-13.2 13.2H13.9C6.6 60.1.7 54.2.7 46.9c0-7.3 5.9-13.2 13.2-13.2H47z"
        fill="#36C5F0"
      />
      <path
        d="M99.9 46.9c0-7.3 5.9-13.2 13.2-13.2 7.3 0 13.2 5.9 13.2 13.2 0 7.3-5.9 13.2-13.2 13.2H99.9V46.9zm-6.6 0c0 7.3-5.9 13.2-13.2 13.2-7.3 0-13.2-5.9-13.2-13.2V13.8C66.9 6.5 72.8.6 80.1.6c7.3 0 13.2 5.9 13.2 13.2v33.1z"
        fill="#2EB67D"
      />
      <path
        d="M80.1 99.8c7.3 0 13.2 5.9 13.2 13.2 0 7.3-5.9 13.2-13.2 13.2-7.3 0-13.2-5.9-13.2-13.2V99.8h13.2zm0-6.6c-7.3 0-13.2-5.9-13.2-13.2 0-7.3 5.9-13.2 13.2-13.2h33.1c7.3 0 13.2 5.9 13.2 13.2 0 7.3-5.9 13.2-13.2 13.2H80.1z"
        fill="#ECB22E"
      />
    </svg>
  )
}
