import { Suspense } from "react";
import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  return (
    <main className="relative flex min-h-dvh items-center justify-center p-4">
      <div className="aurora" aria-hidden />
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
