import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import { AuthProvider } from "@/components/auth-provider";
import "./globals.css";

const inter = Inter({ variable: "--font-interface", subsets: ["latin"] });
const plexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  weight: ["400", "500", "600"],
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "LMPC Workbench",
  description: "Local enforcement workbench for packaged-commodity inspections",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${plexMono.variable}`}>
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
