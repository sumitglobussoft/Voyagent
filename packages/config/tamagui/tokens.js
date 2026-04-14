// Voyagent Tamagui tokens — stub.
//
// The native (Expo / React Native) surface will consume these once Tamagui is
// wired into the mobile app. For now this is a placeholder so the shape of the
// tokens exists and can be referenced by design reviews.
//
// Keep the values in step with the Tailwind preset — the brand palette is one
// source of truth, expressed twice for the two rendering stacks.

const tokens = {
  color: {
    ink: "hsl(222, 47%, 11%)",
    paper: "hsl(0, 0%, 100%)",
    accent: "hsl(262, 83%, 58%)",
    muted: "hsl(215, 16%, 47%)",
  },
  space: {
    0: 0,
    1: 4,
    2: 8,
    3: 12,
    4: 16,
    5: 24,
    6: 32,
  },
  radius: {
    sm: 4,
    md: 8,
    lg: 16,
  },
};

export default tokens;
