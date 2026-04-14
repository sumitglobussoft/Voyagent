/**
 * Test runner setup — pulls in the jest-dom matchers so specs don't have
 * to import them individually. Also stubs `scrollIntoView` which JSDOM
 * doesn't implement but MessageList calls on mount.
 */
import "@testing-library/jest-dom/vitest";

if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {
    /* noop in JSDOM */
  };
}
