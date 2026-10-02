import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Risk Evidence Trace",
  description: "Every point of an underwriting decision traces back to one observation and one rule.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
