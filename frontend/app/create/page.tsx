"use client";

import { BookOpenText } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { NewBookWizard } from "@/components/wizard/new-book-wizard";
import { assetPath } from "@/lib/assets";

export default function CreatePage() {
  const [queryState, setQueryState] = useState({ sourceWork: "", mode: "" });
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setQueryState({ sourceWork: params.get("sourceWork") || "", mode: params.get("mode") || "" });
  }, []);
  const mode = queryState.mode;
  const sourceWork = queryState.sourceWork;
  const pageLabel = sourceWork
    ? mode === "continuation"
      ? "新建续写"
      : mode === "fanfic"
        ? "新建同人"
        : "借鉴技法"
    : "新建原创";
  const title = sourceWork
    ? "先把来源作品变成资料，再建立这本新书自己的主线"
    : "先把一个故事写活，再让它长成一部长篇";
  const subtitle = sourceWork
    ? "同人和续写都从新书向导开始：你确认核心承诺、人物位置和第一章，系统再进入后续写作。"
    : "你说出真正想写的，AI 协助世界、人物与情节彼此成立；读完第一章，再决定是否建立作品。";
  return (
    <main className="min-h-screen pb-10">
      <header className="border-b border-black/10 bg-[#f8f5ee]/90 backdrop-blur-xl">
        <div className="app-frame flex h-16 items-center justify-between">
          <Link href="/bookshelf" className="flex items-center gap-3 font-editorial text-lg font-bold">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#20221f] text-white">
              <BookOpenText size={17} />
            </span>
            浮生流年
          </Link>
          <div className="flex gap-2"><Link href="/bookshelf" className="secondary-button">
              返回书架
            </Link>
          </div>
        </div>
      </header>

      <section className="create-intro" style={{ backgroundImage: `url(${assetPath("/images/writer-desk.jpg")})` }}>
        <div className="app-frame relative z-10 py-9 text-white md:py-11">
          <div className="text-xs font-bold text-[#e1b66b]">{pageLabel}</div>
          <h1 className="mt-3 max-w-3xl font-editorial text-3xl font-bold leading-tight md:text-4xl">{title}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-white/72">{subtitle}</p>
        </div>
      </section>

      <div className="app-frame -mt-1 pb-12 pt-7 md:pt-9"><NewBookWizard /></div>
    </main>
  );
}
