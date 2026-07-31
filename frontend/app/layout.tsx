import "./globals.css";
import type { Metadata } from "next";


export const metadata: Metadata = {
  title: "浮生流年",
  description: "为长篇故事而生的 AI 写作工作台",
};


export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="antialiased">{children}</body>
    </html>
  );
}
