"use server";

import { redirect } from "next/navigation";

import {
  apiErrorCode,
  apiPost,
  type CreateInviteResponse,
} from "@/lib/api";

export async function createInviteAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim();
  const role = String(formData.get("role") ?? "agent").trim();
  if (!email) {
    redirect(
      `/settings?status=err&msg=${encodeURIComponent("Email is required.")}`,
    );
  }
  const res = await apiPost<CreateInviteResponse>("/api/auth/invites", {
    email,
    role,
  });
  if (!res.ok || !res.data) {
    const code = apiErrorCode(res.data) ?? "request_failed";
    let msg = "Could not send invite.";
    if (code === "invite_already_exists") {
      msg = "A pending invite already exists for that email.";
    } else if (code === "forbidden_role") {
      msg = "Only agency admins can send invites.";
    }
    redirect(`/settings?status=err&msg=${encodeURIComponent(msg)}`);
  }
  const link = res.data.invite_link;
  redirect(
    `/settings?status=ok&msg=${encodeURIComponent(
      "Invite sent. Share the link below with your teammate:",
    )}&invite_link=${encodeURIComponent(link)}`,
  );
}

export async function revokeInviteAction(formData: FormData): Promise<void> {
  const id = String(formData.get("invite_id") ?? "").trim();
  if (!id) {
    redirect("/settings?status=err&msg=Missing+invite+id");
  }
  const res = await apiPost(`/api/auth/invites/${id}/revoke`, {});
  if (!res.ok) {
    redirect(
      `/settings?status=err&msg=${encodeURIComponent("Could not revoke invite.")}`,
    );
  }
  redirect(
    `/settings?status=ok&msg=${encodeURIComponent("Invite revoked.")}`,
  );
}
