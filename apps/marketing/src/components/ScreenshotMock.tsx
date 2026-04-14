import { cn } from "@/lib/cn";

export type ScreenshotVariant =
  | "chat"
  | "reconciliation"
  | "quote"
  | "bsp-match"
  | "approval";

export interface ScreenshotMockProps {
  variant: ScreenshotVariant;
  label?: string;
  className?: string;
}

/**
 * A polished CSS/SVG mockup of a Voyagent UI surface.
 *
 * ### Why not real screenshots?
 * Voyagent is in early access — real product screenshots would either be
 * stale or give a misleading snapshot of features still in flux. Rather
 * than fabricate artwork, we render a **plausible product UI** from text
 * and CSS primitives so visitors see concrete product surfaces without
 * us claiming a pixel-perfect current-state UI we can't back up.
 *
 * Every mock carries a small "illustrative" label in the top-right corner
 * so the visitor is explicitly told this is a rendering, not a capture.
 */
export function ScreenshotMock({
  variant,
  label,
  className,
}: ScreenshotMockProps) {
  return (
    <figure
      className={cn(
        "relative overflow-hidden rounded-xl border border-slate-200 bg-white shadow-soft-lg",
        className,
      )}
      aria-label={label ?? `Illustrative ${variant} mockup`}
    >
      <BrowserChrome />
      <div className="relative bg-slate-50 px-4 py-5 md:px-6 md:py-7">
        <span className="pointer-events-none absolute right-3 top-3 rounded-full bg-white/90 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500 ring-1 ring-slate-200">
          Illustrative
        </span>
        {variant === "chat" ? <ChatMock /> : null}
        {variant === "quote" ? <QuoteMock /> : null}
        {variant === "reconciliation" ? <ReconciliationMock /> : null}
        {variant === "bsp-match" ? <BspMatchMock /> : null}
        {variant === "approval" ? <ApprovalMock /> : null}
      </div>
    </figure>
  );
}

function BrowserChrome() {
  return (
    <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-100 px-4 py-2.5">
      <span className="h-2.5 w-2.5 rounded-full bg-rose-300" aria-hidden />
      <span className="h-2.5 w-2.5 rounded-full bg-amber-300" aria-hidden />
      <span
        className="h-2.5 w-2.5 rounded-full bg-emerald-300"
        aria-hidden
      />
      <div className="mx-3 flex-1 rounded-md bg-white px-3 py-1 text-[11px] text-slate-500">
        voyagent.globusdemos.com/app
      </div>
    </div>
  );
}

function Bubble({
  role,
  children,
}: {
  role: "user" | "agent";
  children: React.ReactNode;
}) {
  const isUser = role === "user";
  return (
    <div
      className={cn(
        "max-w-[85%] rounded-2xl px-4 py-3 text-[13px] leading-relaxed",
        isUser
          ? "ml-auto bg-primary text-white"
          : "bg-white text-slate-800 ring-1 ring-slate-200",
      )}
    >
      {children}
    </div>
  );
}

function ChatMock() {
  return (
    <div className="flex flex-col gap-3">
      <Bubble role="user">
        Quote a Dubai 4-night Emirates direct for 2 adults on the 22nd,
        4-star near Downtown.
      </Bubble>
      <Bubble role="agent">
        <div className="font-semibold text-primary">
          Gathered requirements
        </div>
        <ul className="mt-1 space-y-0.5 text-slate-700">
          <li>Sector: BOM &rarr; DXB, 22&ndash;26 Apr</li>
          <li>Pax: 2 adults</li>
          <li>Airline: Emirates (direct only)</li>
          <li>Hotel: 4-star, Downtown Dubai</li>
          <li>Visa: eligible on UAE e-visa (30-day)</li>
        </ul>
        <div className="mt-2 text-slate-500">
          Checking Amadeus + Hotelbeds&hellip;
        </div>
      </Bubble>
      <Bubble role="agent">
        Found 3 fare options and 5 hotel options. Top bundle: EK 501 direct
        &middot; Rove Downtown &middot; total INR 1,47,320. Approve to
        quote?
      </Bubble>
    </div>
  );
}

function QuoteMock() {
  return (
    <div className="rounded-xl bg-white p-5 ring-1 ring-slate-200">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500">
            Quotation Q-2026-0412
          </div>
          <div className="mt-1 text-base font-semibold text-slate-900">
            Aarti Menon &middot; Dubai 4N
          </div>
        </div>
        <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200">
          Draft
        </span>
      </div>
      <table className="mt-4 w-full text-left text-[12.5px]">
        <thead>
          <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500">
            <th className="py-2">Component</th>
            <th className="py-2">Detail</th>
            <th className="py-2 text-right">INR</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 text-slate-800">
          <tr>
            <td className="py-2">Flight</td>
            <td className="py-2">EK 501/500 BOM&ndash;DXB direct</td>
            <td className="py-2 text-right">64,200</td>
          </tr>
          <tr>
            <td className="py-2">Hotel</td>
            <td className="py-2">Rove Downtown, 4N, Deluxe</td>
            <td className="py-2 text-right">58,400</td>
          </tr>
          <tr>
            <td className="py-2">Visa</td>
            <td className="py-2">UAE e-visa &times; 2</td>
            <td className="py-2 text-right">14,120</td>
          </tr>
          <tr>
            <td className="py-2">Transfers</td>
            <td className="py-2">Airport &harr; hotel, sedan</td>
            <td className="py-2 text-right">4,600</td>
          </tr>
        </tbody>
        <tfoot>
          <tr className="border-t border-slate-200 font-semibold text-slate-900">
            <td className="py-2" colSpan={2}>
              Total
            </td>
            <td className="py-2 text-right">1,41,320</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function ReconciliationMock() {
  const rows = [
    {
      desc: "EK ticket 176-2345678",
      internal: "64,200",
      statement: "64,200",
      status: "Match",
    },
    {
      desc: "AI 9W refund ADM",
      internal: "—",
      statement: "2,100",
      status: "Unmatched",
    },
    {
      desc: "Commission credit",
      internal: "3,120",
      statement: "3,120",
      status: "Match",
    },
    {
      desc: "6E 1124 void",
      internal: "8,800",
      statement: "8,800",
      status: "Match",
    },
  ];
  return (
    <div className="rounded-xl bg-white p-5 ring-1 ring-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500">
            Reconciliation &middot; Card statement &middot; Apr week 2
          </div>
          <div className="mt-1 text-base font-semibold text-slate-900">
            HDFC corporate card &middot; ending 4021
          </div>
        </div>
        <span className="rounded-full bg-primary-50 px-2.5 py-0.5 text-[11px] font-medium text-primary ring-1 ring-primary-100">
          27 matched &middot; 1 unmatched
        </span>
      </div>
      <table className="mt-4 w-full text-left text-[12.5px]">
        <thead>
          <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500">
            <th className="py-2">Line</th>
            <th className="py-2 text-right">Internal</th>
            <th className="py-2 text-right">Statement</th>
            <th className="py-2">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 text-slate-800">
          {rows.map((r) => (
            <tr key={r.desc}>
              <td className="py-2">{r.desc}</td>
              <td className="py-2 text-right">{r.internal}</td>
              <td className="py-2 text-right">{r.statement}</td>
              <td className="py-2">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[11px] font-medium ring-1",
                    r.status === "Match"
                      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
                      : "bg-rose-50 text-rose-700 ring-rose-200",
                  )}
                >
                  {r.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BspMatchMock() {
  return (
    <div className="rounded-xl bg-white p-5 ring-1 ring-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500">
            BSPlink India &middot; fortnight 07
          </div>
          <div className="mt-1 text-base font-semibold text-slate-900">
            BSP reconciliation
          </div>
        </div>
        <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
          Ready to remit
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-[12.5px] md:grid-cols-4">
        {[
          { k: "Tickets sold", v: "312" },
          { k: "Refunds", v: "17" },
          { k: "ADM pending", v: "2" },
          { k: "Net payable", v: "₹41,28,610" },
        ].map((s) => (
          <div
            key={s.k}
            className="rounded-lg border border-slate-200 p-3"
          >
            <div className="text-[11px] uppercase tracking-wider text-slate-500">
              {s.k}
            </div>
            <div className="mt-1 text-base font-semibold text-slate-900">
              {s.v}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-lg bg-amber-50 p-3 text-[12.5px] text-amber-800 ring-1 ring-amber-200">
        ADM EK-00214 flagged: fare filing mismatch on PNR KX3P9L. Draft ACM
        reply prepared for senior agent review.
      </div>
    </div>
  );
}

function ApprovalMock() {
  return (
    <div className="rounded-xl bg-white p-5 ring-1 ring-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500">
            Approval required &middot; issue_ticket
          </div>
          <div className="mt-1 text-base font-semibold text-slate-900">
            PNR KX3P9L &middot; EK 501 &middot; 2 adults
          </div>
        </div>
        <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200">
          Side-effect &middot; Irreversible
        </span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-y-2 text-[12.5px] text-slate-700 md:grid-cols-3">
        <div>
          <dt className="text-[11px] uppercase text-slate-500">Fare</dt>
          <dd className="font-semibold text-slate-900">INR 64,200</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase text-slate-500">Tour code</dt>
          <dd className="font-semibold text-slate-900">IT7A4EK</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase text-slate-500">Time limit</dt>
          <dd className="font-semibold text-slate-900">19:30 IST today</dd>
        </div>
      </dl>
      <div className="mt-4 flex gap-2">
        <button
          type="button"
          className="rounded-md bg-primary px-4 py-2 text-[12.5px] font-semibold text-white"
        >
          Approve &amp; issue
        </button>
        <button
          type="button"
          className="rounded-md border border-slate-200 px-4 py-2 text-[12.5px] font-semibold text-slate-700"
        >
          Hold
        </button>
      </div>
    </div>
  );
}
