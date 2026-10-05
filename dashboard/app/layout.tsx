import type { Metadata } from "next";
import localFont from "next/font/local";
import { headers } from "next/headers";
import { themeBootstrap } from "@/lib/theme";
import { ThemeSync } from "@/components/theme-toggle";
import { ProductTourProvider } from "@/components/product-tour-provider";
import "./globals.css";

const geist = localFont({
  src: "./fonts/geist.woff2",
  variable: "--font-geist",
  weight: "100 900",
  display: "swap",
});
const geistMono = localFont({
  src: "./fonts/geistmono.woff2",
  variable: "--font-geist-mono",
  weight: "100 900",
  display: "swap",
});
const archivo = localFont({
  src: "./fonts/archivo.woff2",
  variable: "--font-archivo",
  weight: "500",
  display: "swap",
});

export const metadata: Metadata = {
  title: "LeadZen by Zyene",
  description: "Lead discovery, outreach, and conversations for the Zyene team.",
  applicationName: "LeadZen by Zyene",
  icons: {
    icon: [
      { url: "/brand/leadzen-favicon.ico", type: "image/x-icon", sizes: "16x16 32x32 48x48" },
      { url: "/brand/leadzen-icon-32.png", type: "image/png", sizes: "32x32" },
      { url: "/brand/leadzen-icon-192.png", type: "image/png", sizes: "192x192" },
      { url: "/brand/leadzen-icon-512.png", type: "image/png", sizes: "512x512" },
    ],
    apple: { url: "/brand/leadzen-icon-180.png", type: "image/png", sizes: "180x180" },
  },
  openGraph: {
    title: "LeadZen by Zyene",
    description: "The Zyene team's lead discovery and outreach workspace.",
    siteName: "LeadZen by Zyene",
    type: "website",
  },
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Request-time rendering keeps the policy nonce unique and pages out of CDN caches.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning className={`${geist.variable} ${geistMono.variable} ${archivo.variable}`}>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body><ThemeSync /><ProductTourProvider>{children}</ProductTourProvider></body>
    </html>
  );
}
