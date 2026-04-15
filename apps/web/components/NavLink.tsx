"use client";

/**
 * Client-side nav link that highlights itself when its ``href`` matches
 * the current route. Used by the sidebar's workspace section.
 *
 * Kept deliberately small — a single file instead of a full client
 * sidebar — so the rest of the sidebar (user card, session list fetch,
 * auth check) stays server-rendered.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactElement, ReactNode } from "react";

export interface NavLinkProps {
  href: string;
  label: string;
  icon: ReactNode;
  /**
   * When true, only an exact match highlights. Defaults to false, which
   * also lights up on any deeper path (e.g. ``/enquiries/abc`` lights
   * up the Enquiries link).
   */
  exact?: boolean;
}

export function NavLink({ href, label, icon, exact = false }: NavLinkProps): ReactElement {
  const pathname = usePathname() ?? "/";
  // `usePathname` returns paths without the Next basePath prefix, so
  // ``href="/enquiries"`` matches pathname ``/enquiries`` directly.
  const isActive = exact
    ? pathname === href
    : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 10px",
        borderRadius: 6,
        textDecoration: "none",
        color: "#18181b",
        background: isActive ? "#e4e4e7" : "transparent",
        fontSize: 14,
        fontWeight: isActive ? 600 : 400,
        borderLeft: isActive ? "3px solid #18181b" : "3px solid transparent",
        paddingLeft: isActive ? 7 : 10,
      }}
    >
      <span style={{ display: "inline-flex", width: 16, height: 16 }}>
        {icon}
      </span>
      <span>{label}</span>
    </Link>
  );
}
