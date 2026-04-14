import { cn } from "@/lib/cn";

export interface ArchitectureDiagramProps {
  className?: string;
  compact?: boolean;
}

/**
 * SVG rendering of the Voyagent six-layer architecture.
 *
 * Each layer is a labeled rectangle. We avoid bitmaps so the image stays
 * crisp on every screen, is readable by screen-readers via the
 * `aria-labelledby` reference to a text description, and ships as text
 * inside the server-rendered HTML. The `compact` variant halves vertical
 * spacing for preview use on the landing page.
 */
export function ArchitectureDiagram({
  className,
  compact = false,
}: ArchitectureDiagramProps) {
  const layers = [
    {
      name: "Layer 5 — Clients",
      detail: "Web · Desktop (Tauri) · Mobile (Expo)",
    },
    {
      name: "Layer 4 — Agents",
      detail:
        "Orchestrator · ticketing_visa · hotels_holidays · accounting · document_verifier · reconciler",
    },
    {
      name: "Layer 3 — Tool Runtime",
      detail:
        "Canonical tools with side_effect · reversible · approval flags",
    },
    {
      name: "Layer 2 — Drivers",
      detail:
        "FareSearch · PNR · Hotel · VisaPortal · Accounting · Payment · BSP · Card · Bank · Messaging",
    },
    {
      name: "Layer 1 — Canonical Model",
      detail:
        "Enquiry · Passenger · Itinerary · PNR · Booking · Invoice · JournalEntry · Reconciliation",
    },
    {
      name: "Layer 0 — Platform Services",
      detail:
        "Multi-tenancy · RBAC · Audit log · Approvals · Credential vault · Observability",
    },
  ];

  const rowHeight = compact ? 52 : 64;
  const gap = compact ? 6 : 10;
  const totalHeight = layers.length * rowHeight + (layers.length - 1) * gap;

  return (
    <figure
      role="img"
      aria-labelledby="arch-diagram-title arch-diagram-desc"
      className={cn(
        "rounded-2xl border border-slate-200 bg-white p-5 shadow-soft-md",
        className,
      )}
    >
      <svg
        viewBox={`0 0 600 ${totalHeight}`}
        className="h-auto w-full"
        preserveAspectRatio="xMidYMid meet"
      >
        <title id="arch-diagram-title">
          Voyagent six-layer architecture
        </title>
        <desc id="arch-diagram-desc">
          Stacked rectangles, top to bottom: Clients, Agents, Tool Runtime,
          Drivers, Canonical Model, Platform Services. Each layer depends on
          the layers below it.
        </desc>
        <defs>
          <linearGradient id="layerGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#0B4F71" stopOpacity="0.06" />
            <stop offset="100%" stopColor="#0B4F71" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {layers.map((layer, idx) => {
          const y = idx * (rowHeight + gap);
          return (
            <g key={layer.name}>
              <rect
                x={0}
                y={y}
                width={600}
                height={rowHeight}
                rx={10}
                fill="url(#layerGrad)"
                stroke="#0B4F71"
                strokeOpacity={0.25}
              />
              <text
                x={18}
                y={y + (compact ? 20 : 24)}
                fontSize={compact ? 13 : 14}
                fontWeight={700}
                fill="#0B4F71"
                fontFamily="Inter, system-ui, sans-serif"
              >
                {layer.name}
              </text>
              <text
                x={18}
                y={y + (compact ? 38 : 46)}
                fontSize={compact ? 11 : 12}
                fill="#475569"
                fontFamily="Inter, system-ui, sans-serif"
              >
                {layer.detail}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
