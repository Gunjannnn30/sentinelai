"use client";

// Org settings: GET needs viewer+, PUT needs admin+. Members: GET developer+,
// POST admin+ (admins cannot grant owner — enforced server-side).
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner, errorText, requestIdOf } from "@/components/error-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/hooks/use-auth";
import { API_V1, apiFetch } from "@/lib/api";
import type { MemberOut, OrgSettings, ProjectOut, Role } from "@/lib/types";
import { canAdmin } from "@/lib/role";

export default function SettingsPage() {
  const { me, refresh } = useAuth();
  const { toast } = useToast();
  const isAdmin = canAdmin(me?.role);

  const settings = useApi<OrgSettings>(`${API_V1}/admin/settings`);
  const members = useApi<MemberOut[]>(`${API_V1}/admin/members`);
  const projects = useApi<ProjectOut[]>(`${API_V1}/admin/projects`);

  const [draft, setDraft] = useState<OrgSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [invite, setInvite] = useState({ email: "", role: "viewer" as Role });

  useEffect(() => {
    if (settings.data) setDraft(settings.data);
  }, [settings.data]);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      await apiFetch<OrgSettings>(`${API_V1}/admin/settings`, {
        method: "PUT",
        body: draft,
      });
      toast({ title: "Settings saved." });
      settings.refetch();
      void refresh(); // org name shows in the top bar
    } catch (err) {
      toast({ title: "Save failed", description: errorText(err), variant: "destructive", requestId: requestIdOf(err) });
    } finally {
      setSaving(false);
    }
  };

  const addMember = async () => {
    try {
      await apiFetch(`${API_V1}/admin/members`, {
        method: "POST",
        body: invite,
      });
      toast({ title: "Member added." });
      setInviteOpen(false);
      setInvite({ email: "", role: "viewer" });
      members.refetch();
    } catch (err) {
      toast({ title: "Invite failed", description: errorText(err), variant: "destructive", requestId: requestIdOf(err) });
    }
  };

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Organization profile, retention, limits, and members."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Organization</CardTitle>
          </CardHeader>
          <CardContent>
            {settings.loading ? (
              <Skeleton className="h-48 w-full" />
            ) : settings.error ? (
              <ErrorBanner error={settings.error} onRetry={settings.refetch} />
            ) : draft ? (
              <div className="grid gap-4">
                <div className="grid gap-1.5">
                  <Label htmlFor="s-name">Name</Label>
                  <Input
                    id="s-name"
                    value={draft.name}
                    disabled={!isAdmin}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="s-slug">Slug</Label>
                  <Input
                    id="s-slug"
                    value={draft.slug}
                    disabled={!isAdmin}
                    onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="grid gap-1.5">
                    <Label htmlFor="s-retention">Retention (days)</Label>
                    <Input
                      id="s-retention"
                      inputMode="numeric"
                      value={String(draft.retention_days)}
                      disabled={!isAdmin}
                      onChange={(e) =>
                        setDraft({ ...draft, retention_days: Number(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor="s-rate">Rate limit (req/min)</Label>
                    <Input
                      id="s-rate"
                      inputMode="numeric"
                      value={String(draft.rate_limit_per_minute)}
                      disabled={!isAdmin}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          rate_limit_per_minute: Number(e.target.value) || 0,
                        })
                      }
                    />
                  </div>
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="s-budget">Monthly budget (USD, empty = none)</Label>
                  <Input
                    id="s-budget"
                    inputMode="decimal"
                    value={draft.budget_monthly_usd ?? ""}
                    disabled={!isAdmin}
                    onChange={(e) =>
                      setDraft({ ...draft, budget_monthly_usd: e.target.value || null })
                    }
                  />
                </div>
                {isAdmin ? (
                  <Button onClick={() => void save()} disabled={saving}>
                    {saving ? "Saving…" : "Save settings"}
                  </Button>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Only admins can change organization settings.
                  </p>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Members</CardTitle>
              <Button size="sm" variant="outline" onClick={() => setInviteOpen(true)} disabled={!isAdmin}>
                Add member
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {members.loading ? (
              <Skeleton className="h-32 w-full" />
            ) : members.error ? (
              <ErrorBanner error={members.error} onRetry={members.refetch} />
            ) : !members.data || members.data.length === 0 ? (
              <EmptyState title="No members." />
            ) : (
              <ul className="divide-y">
                {members.data.map((member) => (
                  <li key={member.user_id} className="flex items-center justify-between py-2 text-sm">
                    <div>
                      <p className="font-medium">{member.full_name || member.email}</p>
                      <p className="text-xs text-muted-foreground">{member.email}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {member.teams.map((team) => (
                        <Badge key={team} variant="secondary">
                          {team}
                        </Badge>
                      ))}
                      <Badge variant="outline">{member.role}</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Projects</CardTitle>
          </CardHeader>
          <CardContent>
            {projects.loading ? (
              <Skeleton className="h-24 w-full" />
            ) : projects.error ? (
              <ErrorBanner error={projects.error} onRetry={projects.refetch} />
            ) : !projects.data || projects.data.length === 0 ? (
              <EmptyState title="No projects." description="Projects group requests for scoping and reporting." />
            ) : (
              <ul className="divide-y">
                {projects.data.map((project) => (
                  <li key={project.id} className="py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{project.name}</span>
                      {project.is_default ? <Badge variant="secondary">default</Badge> : null}
                    </div>
                    {project.description ? (
                      <p className="text-xs text-muted-foreground">{project.description}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        title="Add member"
        description="Admins cannot grant the owner role — that stays with the current owner."
        footer={
          <>
            <Button onClick={() => void addMember()} disabled={!invite.email.trim()}>
              Add
            </Button>
            <Button variant="outline" onClick={() => setInviteOpen(false)}>
              Cancel
            </Button>
          </>
        }
      >
        <div className="grid gap-2">
          <Label htmlFor="inv-email">Email</Label>
          <Input
            id="inv-email"
            type="email"
            value={invite.email}
            onChange={(e) => setInvite({ ...invite, email: e.target.value })}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="inv-role">Role</Label>
          <Select
            id="inv-role"
            value={invite.role}
            onChange={(e) => setInvite({ ...invite, role: e.target.value as Role })}
          >
            <option value="viewer">viewer</option>
            <option value="developer">developer</option>
            <option value="admin">admin</option>
          </Select>
        </div>
      </Dialog>
    </div>
  );
}
