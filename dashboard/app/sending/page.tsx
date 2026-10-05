import { redirect } from "next/navigation";
export default async function Page({ searchParams }: { searchParams: Promise<{ review?: string }> }) {
  const { review } = await searchParams;
  redirect(review && /^[0-9a-f-]{36}$/.test(review) ? `/outreach?review=${review}` : "/outreach");
}
