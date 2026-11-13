import type { ReactNode } from "react";

interface IconProps {
  size?: number;
}

const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function Frame({ size = 16, children }: IconProps & { children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export function DisplayIcon({ size }: IconProps) {
  return (
    <Frame size={size}>
      <g {...STROKE}>
        <rect x="1.75" y="2.75" width="12.5" height="8" rx="1.2" />
        <path d="M6.25 13.25h3.5M8 10.75v2.5" />
      </g>
    </Frame>
  );
}

export function SendIcon({ size }: IconProps) {
  return (
    <Frame size={size}>
      <g {...STROKE}>
        <path d="M14.25 1.75 7 9" />
        <path d="M14.25 1.75 9.6 14.1l-2.1-4.6-4.6-2.1 11.35-5.65Z" />
      </g>
    </Frame>
  );
}

export function EyeIcon({ size, off = false }: IconProps & { off?: boolean }) {
  return (
    <Frame size={size}>
      <g {...STROKE}>
        <path d="M1.25 8S3.9 3.75 8 3.75 14.75 8 14.75 8 12.1 12.25 8 12.25 1.25 8 1.25 8Z" />
        <circle cx="8" cy="8" r="1.9" />
        {off && <path d="M2.5 13.5l11-11" />}
      </g>
    </Frame>
  );
}

export function ChevronIcon({ size, up = false }: IconProps & { up?: boolean }) {
  return (
    <Frame size={size}>
      <path {...STROKE} d={up ? "M3.75 9.75 8 5.5l4.25 4.25" : "M3.75 6.25 8 10.5l4.25-4.25"} />
    </Frame>
  );
}

export function TrashIcon({ size }: IconProps) {
  return (
    <Frame size={size}>
      <g {...STROKE}>
        <path d="M2.75 4.5h10.5" />
        <path d="M6.25 4.5V2.9h3.5v1.6" />
        <path d="M4.4 4.5l.5 8.1h6.2l.5-8.1" />
      </g>
    </Frame>
  );
}

export function GripIcon({ size }: IconProps) {
  return (
    <Frame size={size}>
      <g fill="currentColor">
        {[5, 8, 11].map((y) =>
          [6, 10].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.05" />),
        )}
      </g>
    </Frame>
  );
}

export function HelpIcon({ size }: IconProps) {
  return (
    <Frame size={size}>
      <g {...STROKE}>
        <circle cx="8" cy="8" r="6.25" />
        <path d="M6.3 6.1a1.8 1.8 0 0 1 3.5.5c0 1.2-1.8 1.4-1.8 2.6" />
        <path d="M8 11.9v.05" />
      </g>
    </Frame>
  );
}

export function GearIcon({ size }: IconProps) {
  return (
    <Frame size={size}>
      <g {...STROKE}>
        <circle cx="8" cy="8" r="2.1" />
        <path d="M8 1.9v1.6M8 12.5v1.6M2 8h1.6M12.4 8H14M3.7 3.7l1.1 1.1M11.2 11.2l1.1 1.1M12.3 3.7l-1.1 1.1M4.8 11.2l-1.1 1.1" />
      </g>
    </Frame>
  );
}

export function LogoIcon({ size = 20 }: IconProps) {
  return (
    <Frame size={size}>
      <g fill="currentColor">
        <rect x="1.5" y="4" width="2.4" height="8" rx="0.7" />
        <rect x="4.9" y="4" width="2.4" height="8" rx="0.7" opacity="0.75" />
        <rect x="8.3" y="4" width="2.4" height="8" rx="0.7" opacity="0.55" />
        <rect x="11.7" y="4" width="2.4" height="8" rx="0.7" opacity="0.35" />
      </g>
    </Frame>
  );
}
