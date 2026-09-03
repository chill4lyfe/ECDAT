import type { Metadata } from "next";
import { Electrolize, Inter_Tight } from "next/font/google";
import "./globals.css";

const display = Electrolize({
  subsets: ["latin"],
  variable: "--font-display",
  weight: "400",
});

const body = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "ECDAT | Cryptographic Intelligence",
  description: "Enterprise cryptographic discovery, graph analysis, and quantum migration intelligence.",
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
