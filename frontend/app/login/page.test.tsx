import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the pieces of next/navigation + auth the login page touches.
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/login",
}));

const login = vi.fn();
const register = vi.fn();
vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ login, register, me: null, loading: false }),
}));

import LoginPage from "./page";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("login form", () => {
  it("blocks submission and shows errors for empty fields", async () => {
    render(<LoginPage />);
    await userEvent.click(screen.getByRole("tab", { name: "Sign in" }));
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Email is required.")).toBeInTheDocument();
    expect(screen.getByText("Password is required.")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("rejects an invalid email address", async () => {
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "not-an-email");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("submits valid credentials and redirects", async () => {
    login.mockResolvedValue(undefined);
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "dev@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith("dev@example.com", "secret123");
      expect(replace).toHaveBeenCalledWith("/");
    });
  });

  it("shows the register schema requires an 8+ char password", async () => {
    render(<LoginPage />);
    await userEvent.click(screen.getByRole("tab", { name: "Create account" }));
    await userEvent.type(screen.getByLabelText("Full name"), "Dev User");
    await userEvent.type(screen.getByLabelText("Email"), "dev@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.type(screen.getByLabelText("Organization"), "Acme");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Password must be at least 8 characters.")).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });
});
