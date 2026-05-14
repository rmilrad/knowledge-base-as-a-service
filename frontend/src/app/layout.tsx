import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KBaaS",
  description: "Knowledge Base as a Service",
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
