import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  TransformWrapper,
  TransformComponent,
} from 'react-zoom-pan-pinch';
import { Loader2, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import { api } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import type { FloorPlan } from '@/modules/floor-plan/types';

interface FloorPlanViewerProps {
  plan: FloorPlan;
  /** Optional className for the outer container. */
  className?: string;
  /** Show the zoom/reset toolbar. Default true. */
  showControls?: boolean;
  /**
   * Render-prop for content overlaid on top of the image in source-pixel
   * coordinate space. Receives the current zoom scale (for drag math
   * adjustment) and a flag indicating whether the image is currently
   * panning (for cursor styling).
   */
  children?: (api: {
    currentScale: number;
    isPanning: boolean;
  }) => React.ReactNode;
  /**
   * Fired when the user clicks on the image background (not a child).
   * Coordinates are fractional (0..1) in source-image space. Used by
   * the editor for placement-mode click-to-drop.
   */
  onPlaneClick?: (x: number, y: number) => void;
  /**
   * Fired when the user double-clicks anywhere on the plane. Used by
   * the zone editor to finish a polygon. No coordinates because we
   * don't append a vertex at the double-click point — we just close
   * the polygon using the existing draft.
   */
  onPlaneDoubleClick?: () => void;
}

/**
 * Renders a floor plan image with zoom + pan.
 *
 * Auth + blob URL:
 *   The `/floor-plans/:id/image` endpoint requires an Authorization
 *   header, so a plain <img src=...> doesn't work. We fetch the image
 *   via axios (which has the auth interceptor), turn the response into
 *   a blob URL, and use that as the <img src>.
 *
 *   Blob URLs are revoked when the component unmounts or the plan
 *   changes, so we don't leak memory if the operator switches plans.
 */
export function FloorPlanViewer({
  plan,
  className,
  showControls = true,
  children,
  onPlaneClick,
  onPlaneDoubleClick,
}: FloorPlanViewerProps) {
  const { t } = useTranslation();
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Track the current zoom scale so child marker layers can adjust their
  // drag math + visual sizing. Updated by onTransformed below.
  const [currentScale, setCurrentScale] = useState(1);

  // When onPlaneClick OR onPlaneDoubleClick is supplied (i.e. the parent
  // is in placing or drawing mode), we disable the library's panning
  // handler entirely. react-zoom-pan-pinch uses setPointerCapture for
  // pan detection, which redirects pointer events away from our content
  // and breaks click handling (known library issue, #37/#519). Disabling
  // panning lets native clicks reach our onClick handler cleanly. Users
  // pan to position the view BEFORE entering placing mode; this is the
  // standard CAD pattern.
  const placingMode = !!onPlaneClick || !!onPlaneDoubleClick;

  function handleImageClick(e: React.MouseEvent<HTMLElement>) {
    if (!onPlaneClick) return;
    // Compute fractional position from the IMAGE's bounding rect (its
    // visual post-transform rect — click position relative to it gives
    // fractional source-image coords regardless of current zoom/pan).
    const img = e.currentTarget.querySelector('img');
    const rect = (img || e.currentTarget).getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    onPlaneClick(
      Math.max(0, Math.min(1, x)),
      Math.max(0, Math.min(1, y))
    );
  }

  useEffect(() => {
    setImageUrl(null);
    setError(null);
    let revoked = false;
    let createdUrl: string | null = null;

    (async () => {
      try {
        const response = await api.get(`/floor-plans/${plan.id}/image`, {
          responseType: 'blob',
        });
        if (revoked) return;
        createdUrl = URL.createObjectURL(response.data);
        setImageUrl(createdUrl);
      } catch (e: any) {
        if (revoked) return;
        setError(
          e?.response?.status === 404
            ? t('floorPlan.viewer.notFound')
            : t('floorPlan.viewer.loadFailed')
        );
      }
    })();

    return () => {
      revoked = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [plan.id, t]);

  return (
    <div
      className={cn(
        'relative h-full w-full overflow-hidden rounded-md bg-muted/20',
        className
      )}
    >
      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-danger">
          {error}
        </div>
      )}

      {!error && !imageUrl && (
        <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      )}

      {imageUrl && (
        <TransformWrapper
          minScale={0.2}
          maxScale={8}
          initialScale={1}
          centerOnInit
          wheel={{ step: 0.15 }}
          doubleClick={{ mode: 'reset' }}
          panning={{ disabled: placingMode }}
          onTransformed={(_ref, state) => {
            setCurrentScale(state.scale);
          }}
        >
          {({ zoomIn, zoomOut, resetTransform }) => (
            <>
              {showControls && (
                <div className="absolute end-3 top-3 z-10 flex flex-col gap-1.5 rounded-md border border-border bg-background/80 p-1.5 shadow-sm backdrop-blur">
                  <button
                    type="button"
                    onClick={() => zoomIn()}
                    className="rounded p-1.5 text-foreground hover:bg-muted"
                    aria-label={t('floorPlan.viewer.zoomIn')}
                    title={t('floorPlan.viewer.zoomIn')}
                  >
                    <ZoomIn className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => zoomOut()}
                    className="rounded p-1.5 text-foreground hover:bg-muted"
                    aria-label={t('floorPlan.viewer.zoomOut')}
                    title={t('floorPlan.viewer.zoomOut')}
                  >
                    <ZoomOut className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => resetTransform()}
                    className="rounded p-1.5 text-foreground hover:bg-muted"
                    aria-label={t('floorPlan.viewer.fit')}
                    title={t('floorPlan.viewer.fit')}
                  >
                    <Maximize2 className="h-4 w-4" />
                  </button>
                </div>
              )}
              <TransformComponent
                wrapperClass="!h-full !w-full"
                contentClass="!h-full !w-full"
              >
                <div
                  className="relative"
                  style={{
                    width: plan.width_px,
                    height: plan.height_px,
                    cursor: placingMode ? 'crosshair' : 'inherit',
                  }}
                  onClick={handleImageClick}
                  onDoubleClick={onPlaneDoubleClick}
                >
                  <img
                    src={imageUrl}
                    alt={plan.name}
                    className="block h-full w-full select-none pointer-events-none"
                    draggable={false}
                  />
                  {/* Render-prop children — receive the live scale so
                      marker layers can adjust drag math + visual sizing. */}
                  {children?.({ currentScale, isPanning: false })}
                </div>
              </TransformComponent>
            </>
          )}
        </TransformWrapper>
      )}
    </div>
  );
}
