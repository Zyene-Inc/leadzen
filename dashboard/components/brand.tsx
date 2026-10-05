import Image from "next/image";

export function Brand() {
  return (
    <div className="brand" role="img" aria-label="LeadZen by Zyene">
      <div className="brand-copy" aria-hidden="true">
        <Image className="brand-logo brand-logo-light" src="/brand/leadzen-by-zyene-approved-light.png" width={2170} height={725} alt="" loading="eager" unoptimized />
        <Image className="brand-logo brand-logo-dark" src="/brand/leadzen-by-zyene-dark.png" width={1200} height={401} alt="" loading="eager" unoptimized />
      </div>
    </div>
  );
}
