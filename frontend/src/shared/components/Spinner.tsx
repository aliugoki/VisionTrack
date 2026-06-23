import { Loader2 } from 'lucide-react';
import { cn } from '@/shared/lib/cn';

export function Spinner({
  size = 16,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <Loader2
      className={cn('animate-spin text-muted-foreground', className)}
      style={{ width: size, height: size }}
      aria-label="Loading"
    />
  );
}
