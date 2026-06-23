import { cn } from '@/shared/lib/cn';

export function Logo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn('text-primary', className)}
      aria-hidden="true"
    >
      {/* Concentric viewport rings forming a stylised aperture */}
      <rect
        x="2"
        y="2"
        width="28"
        height="28"
        rx="6"
        stroke="currentColor"
        strokeWidth="2"
      />
      <circle cx="16" cy="16" r="8" stroke="currentColor" strokeWidth="2" />
      <circle cx="16" cy="16" r="2.5" fill="currentColor" />
      {/* Crosshair ticks */}
      <line x1="16" y1="6" x2="16" y2="9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="16" y1="23" x2="16" y2="26" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="6" y1="16" x2="9" y2="16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="23" y1="16" x2="26" y2="16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
