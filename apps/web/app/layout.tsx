import type { Metadata } from "next";
import { Electrolize, Geist } from "next/font/google";
import "./globals.css";

const display = Electrolize({
  subsets: ["latin"],
  variable: "--font-display",
  weight: "400",
});

const body = Geist({
  subsets: ["latin"],
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "ECDAT | Enterprise Cryptographic Intelligence",
  description: "Evidence-led cryptographic discovery, quantum risk analysis, dependency mapping, and migration planning for enterprise environments.",
  icons: {
    icon: "/icons/icon.png",
    shortcut: "/icons/icon.png",
    apple: "/icons/icon.png",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${body.variable}`}>{children}</body>
    </html>
  );
}
