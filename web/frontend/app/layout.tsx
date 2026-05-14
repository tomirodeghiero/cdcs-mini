import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CDCS Mini Report Generator",
  description: "Deterministic JSON reports from @generate behavioral contracts.",
};

// Runs before React hydrates — that's how we avoid the light-mode flash on dark machines
const themeBootstrap = `
(function(){
  try{
    var stored = localStorage.getItem('theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (stored === 'dark' || (!stored && prefersDark)) {
      document.documentElement.classList.add('dark');
    }
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className="h-full">{children}</body>
    </html>
  );
}
