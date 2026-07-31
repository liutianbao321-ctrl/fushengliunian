"use client";

import { ArrowRight, BookOpenText, Eye, EyeOff, LoaderCircle, LockKeyhole, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { assetPath } from "@/lib/assets";
import { useAppStore } from "@/lib/store";

export default function HomePage() {
  const router = useRouter();
  const { token, user, hydrate, setSession } = useAppStore();
  const [nickname, setNickname] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (token && user) {
      router.replace("/bookshelf");
    }
  }, [router, token, user]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!nickname.trim() || !password) {
      setError("请填写昵称和密码");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch<{ access_token: string; user: { id: string; nickname: string } }>(
        mode === "login" ? "/auth/login" : "/auth/register",
        { method: "POST", body: JSON.stringify({ nickname: nickname.trim(), password }) },
      );
      setSession(response.access_token, response.user);
      router.push("/bookshelf");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#eef0eb]">
      <div className="grid min-h-screen bg-[#f8f7f2] lg:grid-cols-[minmax(0,1.1fr)_minmax(440px,0.7fr)]">
        <section className="relative min-h-[32vh] overflow-hidden sm:min-h-[38vh] lg:min-h-screen">
          <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url(${assetPath("/images/writer-desk.jpg")})` }} />
          <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(20,22,18,0.08),rgba(20,22,18,0.72))]" />
          <div className="absolute left-6 top-6 flex items-center gap-3 text-white sm:left-10 sm:top-9 xl:left-14">
            <span className="flex h-10 w-10 items-center justify-center rounded-full border border-white/35 bg-black/10 backdrop-blur-md">
              <BookOpenText size={19} strokeWidth={1.7} />
            </span>
            <span className="font-editorial text-xl font-bold">浮生流年</span>
          </div>
          <div className="absolute bottom-7 left-6 max-w-2xl text-white sm:bottom-10 sm:left-10 xl:bottom-16 xl:left-14">
            <div className="mb-3 h-px w-12 bg-[#e3bd77] sm:mb-6 sm:w-16" />
            <blockquote className="font-editorial text-2xl font-semibold leading-[1.45] sm:text-4xl xl:text-5xl">
              把想看的故事，<br />认真写出来。
            </blockquote>
            <p className="mt-3 hidden max-w-lg text-sm leading-7 text-white/75 sm:block sm:mt-7">
              从故事构想、人物设定到每一章初稿，AI 帮你保持连贯，你始终决定故事怎么走。
            </p>
          </div>
        </section>

        <section className="relative flex items-center justify-center border-l border-black/5 bg-[#fbfaf6] px-6 py-10 sm:px-12 lg:px-14">
          <div className="reveal w-full max-w-[390px]">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#4e6859]"><span className="h-px w-7 bg-[#4e6859]" />个人写作空间</div>
            <h1 className="mt-4 font-editorial text-[30px] font-bold leading-tight sm:text-[38px]">
              {mode === "login" ? "回到你的故事" : "建立你的写作空间"}
            </h1>
            <p className="mt-2 text-sm leading-7 text-[#6d6d66]">
              {mode === "login" ? "章节、设定与伏笔，都在原处等你。" : "从一个名字开始，写下属于你的长篇。"}
            </p>

            <div className="mt-7 grid grid-cols-2 border-b border-[#d8d1c4]" role="tablist" aria-label="账号操作">
              {(["login", "register"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  role="tab"
                  aria-selected={mode === item}
                  className={`relative py-3 text-sm font-semibold transition-colors ${mode === item ? "text-[#a63f2f]" : "text-[#77776f] hover:text-[#20221f]"}`}
                  onClick={() => {
                    setMode(item);
                    setError(null);
                  }}
                >
                  {item === "login" ? "登录" : "注册"}
                  {mode === item ? <span className="absolute inset-x-0 -bottom-px h-0.5 bg-[#a63f2f]" /> : null}
                </button>
              ))}
            </div>

            <form className="mt-7 space-y-5" onSubmit={submit}>
              <label className="block">
                <span className="mb-2 block text-xs font-semibold text-[#595b55]">昵称</span>
                <span className="relative block">
                  <UserRound className="absolute left-4 top-1/2 -translate-y-1/2 text-[#89897f]" size={18} />
                  <input
                    className="field h-12 pl-11 pr-4"
                    placeholder="请输入昵称"
                    autoComplete="username"
                    value={nickname}
                    onChange={(event) => setNickname(event.target.value)}
                  />
                </span>
              </label>
              <label className="block">
                <span className="mb-2 block text-xs font-semibold text-[#595b55]">密码</span>
                <span className="relative block">
                  <LockKeyhole className="absolute left-4 top-1/2 -translate-y-1/2 text-[#89897f]" size={18} />
                  <input
                    className="field h-12 px-11"
                    placeholder={mode === "register" ? "至少 8 位字符" : "请输入密码"}
                    type={showPassword ? "text" : "password"}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  <button
                    className="absolute right-3 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center text-[#77776f]"
                    type="button"
                    title={showPassword ? "隐藏密码" : "显示密码"}
                    aria-label={showPassword ? "隐藏密码" : "显示密码"}
                    onClick={() => setShowPassword((value) => !value)}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </span>
              </label>

              <div className="min-h-5" aria-live="polite">
                {error ? <p className="text-sm text-[#a63f2f]">{error}</p> : null}
              </div>

              <button className="primary-button h-12 w-full" disabled={loading} type="submit">
                {loading ? <LoaderCircle className="animate-spin" size={18} /> : null}
                {mode === "login" ? "进入书架" : "创建账号"}
                {!loading ? <ArrowRight size={18} /> : null}
              </button>
            </form>

            <p className="mt-8 text-center text-xs leading-6 text-[#85857d]">你的故事只属于你的账号</p>
          </div>
        </section>
      </div>
    </main>
  );
}
