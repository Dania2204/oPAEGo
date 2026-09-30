import { LoginForm } from "@/components/LoginForm";
import { getSessionUser } from "@/lib/auth";
import { redirect } from "next/navigation";

export default async function HomePage() {
  const user = await getSessionUser();
  if (user?.role === "ADMIN") {
    redirect("/alcaldia");
  }
  if (user?.role === "DRIVER") {
    redirect("/conductor");
  }
  if (user?.role === "USER") {
    redirect("/colegio");
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl items-center justify-center px-6 py-10">
      <section className="w-full max-w-xl">
        <h1 className="text-center text-7xl font-black tracking-tight text-slate-900 sm:text-8xl">PAEGo</h1>
        <div className="mt-8">
          <LoginForm />
        </div>
      </section>
    </main>
  );
}
