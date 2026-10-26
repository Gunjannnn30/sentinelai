// Helpers for turning the backend 422 envelope into per-field messages.
// 422 body shape: { error: { details: { errors: [{ field, message, type }] } } }
import { ApiError } from "@/lib/api";
import type { Api422Details } from "@/lib/types";

export function apiErrorFields(
  error: unknown,
  form?: string,
): Record<string, string> {
  if (!(error instanceof ApiError) || error.status !== 422) return {};
  const details = error.details as Api422Details | null;
  if (!details || !Array.isArray(details.errors)) return {};
  const map: Record<string, string> = {};
  for (const item of details.errors) {
    // FastAPI nests under form.body.* for this app's schemas; strip the prefix
    // so "form.body.email" can be matched against the field named "email".
    const key = form && item.field.startsWith(`${form}.`) ? item.field.slice(form.length + 1) : item.field;
    map[key] = item.message;
  }
  return map;
}
