"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { apiErrorFields } from "@/lib/api-errors";

const loginSchema = z.object({
  email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

const registerSchema = z.object({
  email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
  full_name: z.string().min(1, "Name is required."),
  org_name: z.string().min(1, "Organization name is required."),
});

type LoginForm = z.infer<typeof loginSchema>;
type RegisterForm = z.infer<typeof registerSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [tab, setTab] = useState("login");
  const [formError, setFormError] = useState<unknown>(null);

  const loginForm = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const registerForm = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", full_name: "", org_name: "" },
  });

  const loginFieldErrors = apiErrorFields(formError, "login");

  const onLogin = loginForm.handleSubmit(async (values) => {
    setFormError(null);
    try {
      await login(values.email, values.password);
      router.replace("/");
    } catch (err) {
      setFormError(err);
    }
  });

  const onRegister = registerForm.handleSubmit(async (values) => {
    setFormError(null);
    try {
      await register(values);
      router.replace("/");
    } catch (err) {
      setFormError(err);
    }
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-xl">SentinelAI</CardTitle>
          <CardDescription>Sign in to your workspace or create one.</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs
            tabs={[
              { value: "login", label: "Sign in" },
              { value: "register", label: "Create account" },
            ]}
            value={tab}
            onChange={setTab}
            className="mb-4 w-full"
          />

          {formError instanceof ApiError ? (
            <div role="alert" className="mb-4 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
              <p className="font-medium text-destructive">{formError.message}</p>
              {formError.retryAfter ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Retry after {formError.retryAfter}.
                </p>
              ) : null}
              {formError.requestId ? (
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                  request_id: {formError.requestId}
                </p>
              ) : null}
            </div>
          ) : null}

          <TabPanel value="login" active={tab}>
            <form onSubmit={onLogin} noValidate className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="login-email">Email</Label>
                <Input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  aria-invalid={Boolean(loginForm.formState.errors.email || loginFieldErrors.email)}
                  {...loginForm.register("email")}
                />
                {loginForm.formState.errors.email ? (
                  <p className="text-xs text-destructive">
                    {loginForm.formState.errors.email.message}
                  </p>
                ) : loginFieldErrors.email ? (
                  <p className="text-xs text-destructive">{loginFieldErrors.email}</p>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label htmlFor="login-password">Password</Label>
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  aria-invalid={Boolean(loginForm.formState.errors.password || loginFieldErrors.password)}
                  {...loginForm.register("password")}
                />
                {loginForm.formState.errors.password ? (
                  <p className="text-xs text-destructive">
                    {loginForm.formState.errors.password.message}
                  </p>
                ) : loginFieldErrors.password ? (
                  <p className="text-xs text-destructive">{loginFieldErrors.password}</p>
                ) : null}
              </div>
              <Button type="submit" disabled={loginForm.formState.isSubmitting}>
                {loginForm.formState.isSubmitting ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </TabPanel>

          <TabPanel value="register" active={tab}>
            <form onSubmit={onRegister} noValidate className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="reg-name">Full name</Label>
                <Input id="reg-name" autoComplete="name" {...registerForm.register("full_name")} />
                {registerForm.formState.errors.full_name ? (
                  <p className="text-xs text-destructive">
                    {registerForm.formState.errors.full_name.message}
                  </p>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label htmlFor="reg-email">Email</Label>
                <Input id="reg-email" type="email" autoComplete="email" {...registerForm.register("email")} />
                {registerForm.formState.errors.email ? (
                  <p className="text-xs text-destructive">
                    {registerForm.formState.errors.email.message}
                  </p>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label htmlFor="reg-password">Password</Label>
                <Input
                  id="reg-password"
                  type="password"
                  autoComplete="new-password"
                  {...registerForm.register("password")}
                />
                {registerForm.formState.errors.password ? (
                  <p className="text-xs text-destructive">
                    {registerForm.formState.errors.password.message}
                  </p>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label htmlFor="reg-org">Organization</Label>
                <Input id="reg-org" {...registerForm.register("org_name")} />
                {registerForm.formState.errors.org_name ? (
                  <p className="text-xs text-destructive">
                    {registerForm.formState.errors.org_name.message}
                  </p>
                ) : null}
              </div>
              <Button type="submit" disabled={registerForm.formState.isSubmitting}>
                {registerForm.formState.isSubmitting ? "Creating…" : "Create account"}
              </Button>
            </form>
          </TabPanel>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            <Link href="/" className="underline underline-offset-2">
              Back to app
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
