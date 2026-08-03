import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Set NEXT_PUBLIC_SITE_URL to the real origin at deploy time — it is what makes canonical
// URLs, Open Graph tags, robots.txt and the sitemap emit absolute links instead of localhost.
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const TITLE = "FPL Edge — your gameweek plan";
const DESCRIPTION =
  "Paste your FPL team ID and get a projected score, best captain, best transfer, and a squad-health check. Honest xP, better tooling.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: "%s" },
  description: DESCRIPTION,
  applicationName: "FPL Edge",
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    siteName: "FPL Edge",
    title: TITLE,
    description: DESCRIPTION,
    url: "/",
    locale: "en_GB",
  },
  twitter: { card: "summary", title: TITLE, description: DESCRIPTION },
  // Independent tool — stated in metadata as well as in the footer, so it travels with a share.
  other: {
    "disclaimer": "Not affiliated with, endorsed by, or associated with the Premier League or Fantasy Premier League.",
  },
};

// Runs before paint: applies the saved theme (or the OS preference on first visit) to
// <html> so there's no flash of the wrong theme. `dark:` utilities key off data-theme.
const themeScript = `try{var t=localStorage.getItem('theme');if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.dataset.theme=t;}catch(e){}`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <Nav />
        {children}
        <Footer />
      </body>
    </html>
  );
}
