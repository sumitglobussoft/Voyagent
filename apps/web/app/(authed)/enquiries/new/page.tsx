/**
 * New enquiry page. Server-rendered shell; the form is a client
 * component so it can bind `useFormState` for inline error rendering.
 */
import Link from "next/link";

import { requireUser } from "@/lib/auth";

import { NewEnquiryForm } from "./NewEnquiryForm";

export const metadata = {
  title: "New enquiry · Voyagent",
};

export default async function NewEnquiryPage() {
  await requireUser();

  return (
    <main
      style={{
        maxWidth: 900,
        margin: "0 auto",
        padding: 24,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <p style={{ margin: "0 0 4px 0", fontSize: 13 }}>
        <Link href="/enquiries" style={{ color: "#555" }}>
          ← Enquiries
        </Link>
      </p>
      <h1 style={{ fontSize: 24, margin: "0 0 16px 0" }}>New enquiry</h1>
      <div
        style={{
          padding: 24,
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: 12,
        }}
      >
        <NewEnquiryForm />
      </div>
    </main>
  );
}
