import type { ReactNode } from "react";

export const metadata = {
  title: "Voyagent",
  description: "Agentic operating system for travel agencies.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
