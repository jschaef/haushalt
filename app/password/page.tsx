import { Suspense } from "react";
import { ForcedPassword } from "@/components/forced-password";

// After a login with a one-time password every API call answers
// "password_change_required" until the member sets an own password here.
export default function PasswordPage() {
  return (
    <main className="relative flex min-h-dvh items-center justify-center p-4">
      <div className="aurora" aria-hidden />
      <Suspense>
        <ForcedPassword />
      </Suspense>
    </main>
  );
}
