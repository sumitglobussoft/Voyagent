import Link from "next/link";
import type { ComponentType, SVGProps } from "react";

export interface DomainCardProps {
  title: string;
  summary: string;
  href: string;
  bullets: string[];
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

/**
 * Card for each of the three product domains (ticketing & visa, hotels &
 * holidays, accounting). Renders an icon, title, short summary, a few
 * representative capability bullets, and a link to the domain page.
 */
export function DomainCard({
  title,
  summary,
  href,
  bullets,
  icon: Icon,
}: DomainCardProps) {
  return (
    <Link
      href={href}
      className="group flex flex-col rounded-2xl border border-slate-200 bg-white p-7 shadow-soft-md transition hover:-translate-y-0.5 hover:border-primary-200 hover:shadow-soft-lg"
    >
      <div className="flex items-center gap-3">
        <div className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-white">
          <Icon width={22} height={22} aria-hidden="true" />
        </div>
        <h3 className="text-xl font-semibold tracking-tight text-slate-900">
          {title}
        </h3>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-slate-600">{summary}</p>
      <ul className="mt-5 space-y-2">
        {bullets.map((b) => (
          <li
            key={b}
            className="flex items-start gap-2 text-sm text-slate-700"
          >
            <span
              aria-hidden="true"
              className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent"
            />
            <span>{b}</span>
          </li>
        ))}
      </ul>
      <span className="mt-6 inline-flex items-center gap-1 text-sm font-semibold text-primary">
        Explore
        <span
          aria-hidden="true"
          className="transition group-hover:translate-x-0.5"
        >
          &rarr;
        </span>
      </span>
    </Link>
  );
}
