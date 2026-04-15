/**
 * Route-level loading UI for ``/app/chat``.
 *
 * Centered Voyagent "V" mark plus a short skeleton panel so the
 * chat host's mount isn't a blank white flash. Server component
 * per Next 15 convention.
 */
import { Skeleton } from "@/components/Skeleton";

export default function ChatLoading() {
  return (
    <main
      className="flex flex-1 items-center justify-center p-6"
      style={{ minHeight: "60vh" }}
    >
      <div className="flex w-full max-w-md flex-col items-center gap-4">
        <div
          aria-hidden="true"
          className="flex h-14 w-14 items-center justify-center rounded-full bg-neutral-900 text-2xl font-bold text-neutral-50"
        >
          V
        </div>
        <div
          className="text-sm text-neutral-500"
          role="status"
          aria-live="polite"
        >
          Loading conversation…
        </div>
        <div className="w-full space-y-2">
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/6" />
        </div>
      </div>
    </main>
  );
}
