import type { ReactNode } from "react";
import { HelpTooltip } from "@/components/help-tooltip";

export function PageHeading({ title, help, eyebrow }: { title: string; help: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="page-heading">
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <div className="page-title-row"><h1>{title}</h1><HelpTooltip label={title}>{help}</HelpTooltip></div>
    </div>
  );
}
