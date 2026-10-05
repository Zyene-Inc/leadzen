import { redirect } from "next/navigation";
export default async function Page({ searchParams }: { searchParams: Promise<{ campaign?: string }> }) {
  const { campaign } = await searchParams;
  redirect(campaign && /^[0-9a-f-]{36}$/.test(campaign) ? `/outreach?campaign=${campaign}` : "/outreach");
}
