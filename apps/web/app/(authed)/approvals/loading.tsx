/**
 * Route-level loading UI for ``/app/approvals``.
 *
 * Three card-shaped skeleton placeholders matching the approvals
 * list layout. Server component per Next 15 convention.
 */
import { Skeleton } from "@/components/Skeleton";

export default function ApprovalsLoading() {
  return (
    <main
      style={{
        maxWidth: 900,
        margin: "0 auto",
        padding: 24,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <Skeleton className="mb-4 h-7 w-40" />
      <div className="flex flex-col gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-lg border border-neutral-200 bg-white p-4"
          >
            <div className="mb-3 flex items-center justify-between">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-6 w-20" />
            </div>
            <Skeleton className="mb-2 h-4 w-full" />
            <Skeleton className="mb-2 h-4 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
            <div className="mt-4 flex gap-2">
              <Skeleton className="h-9 w-24" />
              <Skeleton className="h-9 w-24" />
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
