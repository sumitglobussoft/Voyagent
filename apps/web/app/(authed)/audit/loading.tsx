/**
 * Route-level loading UI for ``/app/audit``.
 *
 * Skeleton filter bar plus eight table-row placeholders. Server
 * component per Next 15 convention.
 */
import { Skeleton } from "@/components/Skeleton";

export default function AuditLoading() {
  return (
    <main
      style={{
        maxWidth: 1200,
        margin: "0 auto",
        padding: 24,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <Skeleton className="mb-4 h-7 w-32" />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <Skeleton className="h-9 w-full sm:w-40" />
        <Skeleton className="h-9 w-full sm:w-40" />
        <Skeleton className="h-9 w-full sm:w-64" />
        <Skeleton className="h-9 w-full sm:w-20" />
      </div>
      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
        <div className="flex gap-4 border-b border-neutral-200 bg-neutral-50 p-3">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-4 w-24" />
        </div>
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex gap-4 border-t border-neutral-100 p-3"
          >
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
    </main>
  );
}
