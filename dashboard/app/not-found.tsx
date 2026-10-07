import Link from "next/link";
import { Brand } from "@/components/brand";

export default function NotFound() {
  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="not-found-title">
        <Brand />
        <h1 id="not-found-title">Page not found</h1>
        <p>The page you’re looking for doesn’t exist or may have moved.</p>
        <Link className="button primary" href="/">
          Back to your workspace
        </Link>
      </section>
    </main>
  );
}
