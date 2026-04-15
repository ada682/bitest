import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title:       "CryptoSignals — AI-powered futures scanner",
  description: "Real-time AI signal scanner for MEXC perpetual futures",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
