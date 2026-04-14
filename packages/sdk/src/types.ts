/**
 * Re-export seam for canonical types generated from the Python / Pydantic
 * models in `@voyagent/core`. The SDK owns its own surface of type re-exports
 * so consumers only need a single import to get both the client AND the shapes
 * it moves around.
 *
 * For v0 `@voyagent/core` is still a stub — we re-export a single placeholder
 * type. As real canonical models land (Money, Traveler, Booking, ...) we add
 * the corresponding `export type { ... }` lines here and thread them through
 * the method signatures in `client.ts`.
 */
export type { VoyagentCanonical } from "@voyagent/core";
