import "./globals.css";
import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Audio Notes",
  description: "Upload audio, get a transcript and a summary.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="wrap">
          <header className="nav">
            <h1><Link href="/">🎙 Audio Notes</Link></h1>
            <Link href="/architecture">Architecture</Link>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
