/**
 * Route-level loading UI for ``/app/enquiries``.
 *
 * Renders during the async server render of ``page.tsx`` (which
 * fetches from the API). Replaces the old plain "Loading..." text
 * with a skeleton header + filter bar + a short table of row
 * placeholders so the layout doesn't shift when data arrives.
 *
 * Server component — per Next 15 App Router ``loading.tsx`` convention.
 */
import { Skeleton } from "@/components/Skeleton";

export default function EnquiriesLoading() {
  return (
    <main
      style={{
        maxWidth: 1200,
        margin: "0 auto",
        padding: 24,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div className="mb-4 flex items-center justify-between">
        <Skeleton className="h-7 w-36" />
        <Skeleton className="h-9 w-32" />
      </div>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <Skeleton className="h-9 w-full sm:w-32" />
        <Skeleton className="h-9 w-full sm:w-64" />
        <Skeleton className="h-9 w-full sm:w-20" />
      </div>
      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
        <div className="flex gap-4 border-b border-neutral-200 bg-neutral-50 p-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-12" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-20" />
        </div>
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="flex gap-4 border-t border-neutral-100 p-3"
          >
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-8" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-20" />
          </div>
        ))}
      </div>
    </main>
  );
}
