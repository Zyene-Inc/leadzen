import { profileLink } from "@/lib/discovery";

export function LeadLinks({ linkedin, website }: { linkedin: string; website: string }) {
  const profile = profileLink(linkedin);
  const company = profileLink(website);
  return <div className="lead-links">
    {profile && <a className="text-link" href={profile} target="_blank" rel="noopener noreferrer">LinkedIn <span className="sr-only">(opens in a new tab)</span>↗</a>}
    {company && <a className="text-link" href={company} target="_blank" rel="noopener noreferrer">Company website <span className="sr-only">(opens in a new tab)</span>↗</a>}
  </div>;
}
