/**
 * Ambient types for Expo's inlined `process.env.EXPO_PUBLIC_*` variables.
 *
 * Expo / Metro replaces `process.env.EXPO_PUBLIC_*` references at bundle
 * time (see https://docs.expo.dev/guides/environment-variables/), but
 * `expo/tsconfig.base` doesn't pull in `@types/node`, so TS doesn't know
 * `process` exists. Declaring only the surface we actually read keeps the
 * type gate honest without dragging Node's globals into RN code.
 */
declare const process: {
  readonly env: {
    readonly EXPO_PUBLIC_VOYAGENT_API_URL?: string;
    readonly EXPO_PUBLIC_VOYAGENT_TENANT_ID?: string;
    readonly EXPO_PUBLIC_VOYAGENT_ACTOR_ID?: string;
    readonly [key: string]: string | undefined;
  };
};
