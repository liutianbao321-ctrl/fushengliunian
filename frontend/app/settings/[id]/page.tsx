"use client";

import {
  ArrowLeft,
  BookOpenText,
  Boxes,
  Clock3,
  ChevronRight,
  GitBranch,
  Lightbulb,
  ListTree,
  LoaderCircle,
  Map,
  Palette,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Trash2,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { CharterEditor } from "@/components/writing-charter-editor";

type BiblePage = { id: string; title: string; category: string; content: string };
type Outline = { id: string; parent_id?: string | null; level: string; sequence: number; title: string; content: Record<string, unknown> };
type Foreshadowing = { id: string; content: string; planted_chapter: number; status: string };
type ChapterDirectoryItem = { id: string; volume_sequence: number; chapter_sequence: number; title: string; summary: string; status: string; word_count: number; has_plan: boolean; has_content: boolean; updated_at: string };
type Tab = "创作方向" | "角色" | "世界观" | "卷纲" | "章节目录" | "伏笔" | "时间线";

const tabIcons = {
  角色: UsersRound,
  创作方向: Palette,
  世界观: Map,
  卷纲: GitBranch,
  章节目录: ListTree,
  伏笔: Lightbulb,
  时间线: Clock3,
};

export default function SettingsPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const { token, hydrate } = useAppStore();
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<Tab>("创作方向");
  const [projectTitle, setProjectTitle] = useState("");
  const [styleProfile, setStyleProfile] = useState<Record<string, unknown>>({});
  const [bible, setBible] = useState<BiblePage[]>([]);
  const [outlines, setOutlines] = useState<Outline[]>([]);
  const [foreshadowing, setForeshadowing] = useState<Foreshadowing[]>([]);
  const [timeline, setTimeline] = useState<{ items: BiblePage[] }>({ items: [] });
  const [chapters, setChapters] = useState<ChapterDirectoryItem[]>([]);
  const [totalChapters, setTotalChapters] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    hydrate();
    setReady(true);
  }, [hydrate]);

  useEffect(() => {
    if (!ready) return;
    if (!token) {
      router.replace("/");
      return;
    }
    setLoading(true);
    Promise.all([
      apiFetch<{ title: string; style_profile: Record<string, unknown>; total_chapters: number }>(`/projects/${projectId}`, {}, token),
      apiFetch<BiblePage[]>(`/projects/${projectId}/bible`, {}, token),
      apiFetch<Outline[]>(`/projects/${projectId}/outlines`, {}, token),
      apiFetch<Foreshadowing[]>(`/projects/${projectId}/foreshadowing`, {}, token),
      apiFetch<{ items: BiblePage[] }>(`/projects/${projectId}/timeline`, {}, token),
      apiFetch<ChapterDirectoryItem[]>(`/projects/${projectId}/chapter-directory`, {}, token),
    ])
      .then(([project, biblePages, outlineNodes, foreshadowingItems, timelineData, chapterItems]) => {
        setProjectTitle(project.title);
        setStyleProfile(project.style_profile ?? {});
        setBible(biblePages);
        setOutlines(outlineNodes);
        setForeshadowing(foreshadowingItems);
        setTimeline(timelineData);
        setChapters(chapterItems);
        setTotalChapters(project.total_chapters);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "设定加载失败"))
      .finally(() => setLoading(false));
  }, [projectId, ready, router, token]);

  const characterPages = bible.filter((item) => item.category === "character");
  const nonCharacterPages = bible.filter((item) => item.category !== "character");
  const worldPages = bible.filter((item) => ["worldview", "canon_rule", "location"].includes(item.category) && item.title !== "作者创作宪章");
  const counts: Record<Tab, number> = {
    角色: characterPages.length,
    创作方向: Object.keys(styleProfile).length ? 1 : 0,
    世界观: worldPages.length,
    卷纲: outlines.filter((item) => item.level === "volume").length,
    章节目录: chapters.length,
    伏笔: foreshadowing.length,
    时间线: timeline.items.length,
  };

  return (
    <main className="min-h-screen pb-12">
      <header className="border-b border-black/10 bg-[#f8f5ee]/92 backdrop-blur-xl">
        <div className="app-frame flex min-h-16 items-center justify-between gap-3 py-2">
          <div className="flex min-w-0 items-center gap-3">
            <Link href={`/workspace/${projectId}`} className="icon-button shrink-0" title="返回工作台" aria-label="返回工作台"><ArrowLeft size={17} /></Link>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[11px] text-[#7f8078]"><BookOpenText size={13} /> {projectTitle || "作品设定"}</div>
              <h1 className="mt-0.5 truncate font-editorial text-lg font-bold sm:text-xl">设定管理</h1>
            </div>
          </div>
          <Link href={`/workspace/${projectId}`} className="secondary-button"><span className="hidden sm:inline">返回工作台</span><ArrowLeft className="sm:hidden" size={16} /></Link>
        </div>
      </header>

      <div className="app-frame pt-9">
        <section className="reveal max-w-3xl">
          <div className="eyebrow">Story Bible</div>
          <h2 className="page-title mt-4">让每一条设定，都有迹可循</h2>
          <p className="mt-4 text-sm leading-7 text-[#6c6e67]">角色、规则、事件和伏笔共同组成可持续演进的故事世界。</p>
        </section>

        <nav className="scrollbar-thin reveal reveal-delay-1 mt-8 flex gap-1 overflow-x-auto border-b border-[#d2cbbf]" aria-label="设定分类">
          {(Object.keys(tabIcons) as Tab[]).map((item) => {
            const Icon = tabIcons[item];
            return (
              <button
                key={item}
                type="button"
                className={`relative flex min-w-max items-center gap-2 px-4 pb-3 pt-2 text-sm font-semibold transition ${tab === item ? "text-[#a63f2f]" : "text-[#777870] hover:text-[#20221f]"}`}
                onClick={() => setTab(item)}
              >
                <Icon size={16} /> {item}
                <span className={`rounded-full px-2 py-0.5 text-[10px] ${tab === item ? "bg-[#f0ddd8]" : "bg-[#e8e2d8]"}`}>{counts[item]}</span>
                {tab === item ? <span className="absolute inset-x-2 bottom-0 h-0.5 bg-[#a63f2f]" /> : null}
              </button>
            );
          })}
        </nav>

        {loading ? <div className="mt-7 grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map((item) => <div key={item} className="h-44 animate-pulse rounded-lg border border-black/10 bg-white/45" />)}</div> : null}

        {!loading && error ? (
          <div className="mt-7 flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed border-[#c4b2a5] bg-white/40 text-center">
            <p className="text-sm text-[#a63f2f]">{error}</p>
            <button className="secondary-button mt-4" type="button" onClick={() => window.location.reload()}><RefreshCw size={16} />重新加载</button>
          </div>
        ) : null}

        {!loading && !error ? (
          <div key={tab} className="reveal mt-7">
            {tab === "角色" ? <CharacterManager projectId={projectId} token={token} items={characterPages} onChange={(items) => setBible([...nonCharacterPages, ...items])} /> : null}
            {tab === "创作方向" ? (
              <>
                <StyleManager projectId={projectId} token={token} profile={styleProfile} onChange={setStyleProfile} />
                <CharterEditor projectId={projectId} token={token} />
              </>
            ) : null}
            {tab === "世界观" ? <WorldManager projectId={projectId} token={token} items={worldPages} empty="世界观设定将在初始规划完成后出现。" onChange={(items) => setBible([...bible.filter((page) => !worldPages.some((world) => world.id === page.id)), ...items])} /> : null}
            {tab === "卷纲" ? (
              outlines.length ? (
                <OutlineTree projectId={projectId} token={token} outlines={outlines} onChange={setOutlines} />
              ) : <EmptyState text="大纲节点将在规划任务完成后出现。" />
            ) : null}
            {tab === "章节目录" ? <ChapterDirectory projectId={projectId} items={chapters} totalChapters={totalChapters} /> : null}
            {tab === "伏笔" ? (
              foreshadowing.length ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {foreshadowing.map((item) => (
                    <article key={item.id} className="rounded-lg border border-black/10 bg-[#fbfaf6]/88 p-5 shadow-[0_8px_26px_rgba(45,39,30,0.05)]">
                      <div className="flex items-center justify-between gap-3">
                        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#f2e6cf] text-[#a06f22]"><Lightbulb size={17} /></span>
                        <span className="rounded-full bg-[#edf1ec] px-3 py-1 text-[11px] text-[#4e6859]">{item.status}</span>
                      </div>
                      <p className="mt-5 font-editorial text-lg font-semibold leading-8">{item.content}</p>
                      <p className="mt-4 border-t border-[#e0d9ce] pt-3 text-xs text-[#837766]">埋设于第 {item.planted_chapter} 章</p>
                    </article>
                  ))}
                </div>
              ) : <EmptyState text="尚未埋设伏笔。" />
            ) : null}
            {tab === "时间线" ? (
              timeline.items.length ? (
                <div className="relative ml-3 border-l border-[#cdbda8] pl-7">
                  {timeline.items.map((item) => (
                    <article key={item.id} className="relative mb-5 rounded-lg border border-black/10 bg-[#fbfaf6]/88 p-5 shadow-[0_8px_26px_rgba(45,39,30,0.05)] last:mb-0">
                      <span className="absolute -left-[35px] top-7 h-3 w-3 rounded-full border-2 border-[#a63f2f] bg-[#f3efe6]" />
                      <h3 className="font-editorial text-xl font-bold">{item.title}</h3>
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-[#64665f]">{item.content}</p>
                    </article>
                  ))}
                </div>
              ) : <EmptyState text="时间线将在故事事件产生后建立。" />
            ) : null}
          </div>
        ) : null}
      </div>
    </main>
  );
}

function CharacterManager({ projectId, token, items, onChange }: { projectId: string; token: string | null; items: BiblePage[]; onChange: (items: BiblePage[]) => void }) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  async function addCharacter() {
    if (!token || !name.trim() || !content.trim()) return;
    try {
      const created = await apiFetch<BiblePage>(`/projects/${projectId}/bible`, { method: "POST", body: JSON.stringify({ category: "character", title: name.trim(), content: content.trim(), aliases: [] }) }, token);
      onChange([...items, created]); setName(""); setContent(""); setAdding(false); setMessage("人物已加入设定库，后续章纲可以安排其登场");
    } catch (err) { setMessage(err instanceof Error ? err.message : "添加人物失败"); }
  }
  async function removeCharacter(id: string) {
    if (!token || !window.confirm("删除这个人物设定？已有正文不会被修改。")) return;
    await apiFetch(`/projects/${projectId}/bible/${id}`, { method: "DELETE" }, token);
    onChange(items.filter((item) => item.id !== id));
  }
  return <div>
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#4e6859]/25 bg-[#edf1ec] p-4"><div><strong className="text-sm">人物会随故事逐步增加</strong><p className="mt-1 text-xs leading-5 text-[#596159]">只保留当前阶段有用的人物。你可以随时手动添加；卷纲规划也会建议需要的新角色。</p></div><button className="primary-button" type="button" onClick={() => setAdding((value) => !value)}><Plus size={16} />添加人物</button></div>
    {adding ? <div className="mb-5 rounded-lg border border-[#d8d0c2] bg-white p-5"><div className="grid gap-4 md:grid-cols-2"><label className="form-label">人物姓名<input className="field mt-2 h-11 px-3" value={name} onChange={(event) => setName(event.target.value)} /></label><label className="form-label">身份、欲望、性格和关系<textarea className="field mt-2 min-h-28 p-3" value={content} onChange={(event) => setContent(event.target.value)} placeholder="例如：前期对手。想得到……；弱点……；与主角……" /></label></div><button className="primary-button mt-4" type="button" disabled={!name.trim() || !content.trim()} onClick={addCharacter}><Save size={16} />保存人物</button></div> : null}
    {message ? <p className="mb-4 text-sm text-[#4e6859]">{message}</p> : null}
    {items.length ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map((page) => <article key={page.id} className="min-h-52 rounded-lg border border-black/10 bg-[#fbfaf6]/88 p-5"><div className="flex items-center justify-between"><span className="text-[11px] font-semibold text-[#a63f2f]">人物设定</span><button className="text-[#8d8174] hover:text-[#a63f2f]" type="button" title="删除人物" onClick={() => removeCharacter(page.id)}><Trash2 size={15} /></button></div><h3 className="mt-4 font-editorial text-2xl font-bold">{page.title}</h3><p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-[#656760]">{page.content}</p></article>)}</div> : <EmptyState text="还没有人物。先添加主角和前期会登场的人即可。" />}
  </div>;
}

function StyleManager({ projectId, token, profile, onChange }: { projectId: string; token: string | null; profile: Record<string, unknown>; onChange: (profile: Record<string, unknown>) => void }) {
  const selected = (profile.selected_style ?? {}) as Record<string, string>;
  const contract = (profile.writing_contract ?? {}) as Record<string, unknown>;
  const author = (profile.author_constitution ?? {}) as Record<string, string>;
  const blueprint = (profile.creation_blueprint ?? {}) as Record<string, unknown>;
  const bookBlueprint = (blueprint.book_blueprint ?? {}) as Record<string, unknown>;
  const worldEngine = (blueprint.world_engine ?? {}) as Record<string, unknown>;
  const [readerPromise, setReaderPromise] = useState(author.reader_promise ?? String(bookBlueprint.reader_promise ?? blueprint.reader_promise ?? worldEngine.reader_promise ?? ""));
  const [whyWrite, setWhyWrite] = useState(author.why_write ?? "");
  const [lastingFeeling, setLastingFeeling] = useState(author.lasting_feeling ?? "");
  const [nonNegotiables, setNonNegotiables] = useState(author.non_negotiables ?? "");
  const [aiMandate, setAiMandate] = useState(author.ai_mandate ?? "在确认的边界内自动规划和写初稿，方向变化先问我");
  const [chapterTest, setChapterTest] = useState(author.chapter_test ?? "本章是否兑现读者期待，并由人物选择改变局面");
  const [prose, setProse] = useState(selected.prose_style ?? String(contract.author_style ?? "自然克制"));
  const [pov, setPov] = useState(selected.pov_style ?? String(contract.pov ?? "第三人称限知"));
  const [pace, setPace] = useState(selected.pace ?? String(contract.rhythm ?? "均衡"));
  const [message, setMessage] = useState<string | null>(null);
  async function save() {
    if (!token) return;
    const next = {
      ...profile,
      author_constitution: { ...author, reader_promise: readerPromise.trim(), why_write: whyWrite.trim(), lasting_feeling: lastingFeeling.trim(), non_negotiables: nonNegotiables.trim(), ai_mandate: aiMandate, chapter_test: chapterTest.trim() },
      creation_blueprint: { ...blueprint, reader_promise: readerPromise.trim(), book_blueprint: { ...bookBlueprint, reader_promise: readerPromise.trim() } },
      selected_style: { prose_style: prose, pov_style: pov, pace },
      writing_contract: { ...contract, author_style: prose, pov, rhythm: pace, reader_contract: `读者持续得到：${readerPromise.trim()}。场景清楚、人物目标可感、秘密有理解支点。` },
    };
    const result = await apiFetch<{ style_profile: Record<string, unknown> }>(`/projects/${projectId}`, { method: "PATCH", body: JSON.stringify({ style_profile: next }) }, token);
    onChange(result.style_profile); setMessage("创作方向已保存，后续卷纲、章纲、正文和检查都会使用");
  }
  return <div className="max-w-5xl border-y border-[#d8d0c2] bg-[#fbfaf6]/75 px-1 py-7 sm:px-7">
    <div className="max-w-3xl"><div className="text-xs font-semibold text-[#a63f2f]">整本书持续生效</div><h3 className="mt-1 font-editorial text-2xl font-bold">作者与读者约定</h3><p className="mt-2 text-sm leading-7 text-[#686a64]">创建作品时的选择都在这里。后续规划先检查读者会得到什么，再检查故事有没有偏离你的心意。</p></div>
    <div className="mt-7 grid gap-5 md:grid-cols-2">
      <label className="form-label md:col-span-2">读者为什么愿意一直读下去<textarea className="field mt-2 min-h-24 p-3 font-normal leading-6" value={readerPromise} onChange={(event) => setReaderPromise(event.target.value)} placeholder="例如：每一卷都看见主角用更艰难的选择换来成长，并改变一段重要关系。" /></label>
      <label className="form-label">读完后希望留下什么感受<textarea className="field mt-2 min-h-24 p-3 font-normal leading-6" value={lastingFeeling} onChange={(event) => setLastingFeeling(event.target.value)} /></label>
      <label className="form-label">为了好看也不能牺牲什么<textarea className="field mt-2 min-h-24 p-3 font-normal leading-6" value={nonNegotiables} onChange={(event) => setNonNegotiables(event.target.value)} /></label>
      <label className="form-label md:col-span-2">AI 与我怎样分工<select className="field mt-2 h-11 px-3" value={aiMandate} onChange={(event) => setAiMandate(event.target.value)}><option value="只给一个经过压力测试的方案，不替我决定方向">AI 给方案，我决定方向</option><option value="在确认的边界内自动规划和写初稿，方向变化先问我">AI 规划并写初稿，方向变化先问我</option><option value="在创作宪章内自动推进整卷，只在质量门失败时停下来">AI 按约定连续写，出现硬伤时停下</option></select></label>
    </div>
    <details className="mt-6 border-t border-[#ddd6cb] pt-4"><summary className="cursor-pointer text-sm font-semibold text-[#555852]">更多写法设置</summary><div className="mt-5 grid gap-5 md:grid-cols-3"><label className="form-label">文字质感<select className="field mt-2 h-11 px-3" value={prose} onChange={(event) => setProse(event.target.value)}>{["自然克制", "细腻沉浸", "爽利明快", "幽默鲜活", "厚重有质感", "诡谲悬疑"].map((item) => <option key={item}>{item}</option>)}</select></label><label className="form-label">叙事视角<select className="field mt-2 h-11 px-3" value={pov} onChange={(event) => setPov(event.target.value)}>{["第三人称限知", "第一人称", "多视角"].map((item) => <option key={item}>{item}</option>)}</select></label><label className="form-label">整体节奏<select className="field mt-2 h-11 px-3" value={pace} onChange={(event) => setPace(event.target.value)}>{["均衡", "紧凑", "慢热"].map((item) => <option key={item}>{item}</option>)}</select></label><label className="form-label md:col-span-3">我为什么想写它<textarea className="field mt-2 min-h-20 p-3 font-normal" value={whyWrite} onChange={(event) => setWhyWrite(event.target.value)} /></label><label className="form-label md:col-span-3">每章内部验收问题<input className="field mt-2 h-11 px-3 font-normal" value={chapterTest} onChange={(event) => setChapterTest(event.target.value)} /></label></div></details>
    <div className="mt-6 border-l-2 border-[#4e6859] bg-[#edf1ec] px-4 py-3 text-sm leading-6 text-[#4d5d52]"><strong>所有题材共同底线：</strong>读者要知道谁在做什么、为什么现在做；秘密可以晚揭晓，正在发生的事不能故意写得看不懂。</div>
    <div className="mt-6 flex flex-wrap items-center gap-3"><button className="primary-button" type="button" disabled={!readerPromise.trim()} onClick={save}><Save size={16} />保存创作方向</button>{message ? <span className="text-sm text-[#4e6859]">{message}</span> : null}</div>
  </div>;
}

function WorldManager({ projectId, token, items, empty, onChange }: { projectId: string; token: string | null; items: BiblePage[]; empty: string; onChange: (items: BiblePage[]) => void }) {
  const [selected, setSelected] = useState<BiblePage | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  if (!items.length) return <EmptyState text={empty} />;
  async function save() {
    if (!token || !selected || !draft.trim()) return;
    setSaving(true); setMessage(null);
    try {
      const updated = await apiFetch<BiblePage>(`/projects/${projectId}/bible/${selected.id}`, { method: "PUT", body: JSON.stringify({ content: draft.trim() }) }, token);
      onChange(items.map((item) => item.id === updated.id ? updated : item));
      setSelected(updated); setDraft(updated.content); setMessage("设定已保存，后续规划、写作和检查都会使用");
    } catch (err) { setMessage(err instanceof Error ? err.message : "保存设定失败"); }
    finally { setSaving(false); }
  }
  return (
    <><div className="stagger-list grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((page) => (
        <button type="button" key={page.id} className="min-h-52 rounded-lg border border-black/10 bg-[#fbfaf6]/88 p-5 text-left shadow-[0_8px_26px_rgba(45,39,30,0.05)] transition hover:-translate-y-1 hover:border-[#a63f2f]/30" onClick={() => { setSelected(page); setDraft(page.content); setMessage(null); }}>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[11px] font-semibold uppercase text-[#a63f2f]">{page.category}</span>
            <span className="h-px w-10 bg-[#b88937]" />
          </div>
          <h3 className="mt-4 font-editorial text-2xl font-bold">{page.title}</h3>
          <p className="mt-4 line-clamp-5 whitespace-pre-wrap text-sm leading-7 text-[#656760]">{page.content}</p>
          <span className="mt-4 flex items-center gap-1 text-xs font-semibold text-[#a63f2f]">查看与编辑<ChevronRight size={14} /></span>
        </button>
      ))}
    </div>{selected ? <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-3 sm:p-6" role="dialog" aria-modal="true" aria-label={selected.title}><div className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-md bg-[#f8f5ee] shadow-2xl"><header className="flex items-center justify-between border-b border-[#d8d0c2] px-5 py-4"><div><div className="text-xs font-semibold uppercase text-[#a63f2f]">{selected.category}</div><h3 className="mt-1 font-editorial text-2xl font-bold">{selected.title}</h3></div><button className="icon-button" type="button" onClick={() => setSelected(null)} title="关闭" aria-label="关闭"><X size={18} /></button></header><div className="scrollbar-thin flex-1 overflow-y-auto p-5 sm:p-7"><textarea className="field min-h-[360px] p-4 font-editorial text-base leading-8" value={draft} onChange={(event) => setDraft(event.target.value)} />{message ? <p className="mt-3 text-sm text-[#4e6859]">{message}</p> : null}</div><footer className="flex justify-end gap-2 border-t border-[#d8d0c2] bg-white/55 px-5 py-4"><button className="secondary-button" type="button" onClick={() => setSelected(null)}>关闭</button><button className="primary-button" type="button" disabled={saving || !draft.trim()} onClick={save}>{saving ? <LoaderCircle className="animate-spin" size={15} /> : <Save size={15} />}{saving ? "正在保存" : "保存设定"}</button></footer></div></div> : null}</>
  );
}

function ChapterDirectory({ projectId, items, totalChapters }: { projectId: string; items: ChapterDirectoryItem[]; totalChapters: number }) {
  const [query, setQuery] = useState("");
  const keyword = query.trim().toLowerCase();
  const filtered = keyword ? items.filter((item) => `${item.chapter_sequence}${item.title}${item.summary}`.toLowerCase().includes(keyword)) : items;
  const volumes = Array.from(new Set(filtered.map((item) => item.volume_sequence))).sort((a, b) => a - b);
  const written = items.filter((item) => item.has_content).length;
  const planned = items.filter((item) => item.has_plan).length;
  return <div className="max-w-5xl">
    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#d8d0c2] pb-5"><div><h3 className="font-editorial text-2xl font-bold">章节目录</h3><p className="mt-2 text-xs text-[#74756e]">已写 {written} 章 · 已规划 {planned} 章 · 全书预计 {totalChapters} 章</p></div><label className="relative block w-full sm:w-72"><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8b8a81]" size={15} /><input className="field h-10 pl-9 pr-3 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索章号、章名或摘要" /></label></div>
    {filtered.length ? <div className="mt-5 space-y-7">{volumes.map((volume) => <section key={volume}><div className="mb-2 text-xs font-semibold text-[#8c7a62]">第 {volume} 卷</div><div className="divide-y divide-[#ded8cd] border-y border-[#ded8cd]">{filtered.filter((item) => item.volume_sequence === volume).map((item) => <Link key={item.id} href={`/workspace/${projectId}?chapter=${item.chapter_sequence}`} className="grid min-h-16 grid-cols-[56px_minmax(0,1fr)_auto] items-center gap-3 px-2 py-3 transition hover:bg-white/55"><span className="text-center text-sm font-semibold tabular-nums text-[#8a8174]">{item.chapter_sequence}</span><span className="min-w-0"><strong className="block truncate text-sm">{item.title || `第 ${item.chapter_sequence} 章`}</strong><span className="mt-1 block truncate text-xs text-[#85857d]">{item.summary || (item.has_plan ? "章纲已准备" : "尚未规划")}</span></span><span className="text-right text-[11px] text-[#777970]">{item.has_content ? `${item.word_count.toLocaleString()} 字` : item.has_plan ? "待写" : "未规划"}</span></Link>)}</div></section>)}</div> : <EmptyState text={keyword ? "没有匹配章节。" : "章节会在规划后出现在这里。"} />}
  </div>;
}

type VolumePlan = {
  title: string; goal: string; opening?: string; new_elements?: Record<string, string>;
  turning_points?: string[]; climax?: string; ending_hook?: string; suggested_chapters?: number;
  foreshadowing_to_resolve?: string[];
  arcs: { sequence: number; title: string; goal: string; conflict: string; climax: string; resolution: string; estimated_chapters: number; involved_characters?: string[] }[];
};

function OutlineTree({ projectId, token, outlines, onChange }: {
  projectId: string; token: string | null; outlines: Outline[]; onChange: (value: Outline[]) => void;
}) {
  const [planning, setPlanning] = useState<number | null>(null);
  const [editor, setEditor] = useState<{ sequence: number; plan: VolumePlan; source: "saved" | "ai"; brief_summary?: { active_foreshadowing_count: number; overdue_count: number } } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const book = outlines.find((item) => item.level === "book");
  const volumes = outlines.filter((item) => item.level === "volume").sort((a, b) => a.sequence - b.sequence);
  const arcs = outlines.filter((item) => item.level === "arc");

  async function generatePlan(sequence: number) {
    if (!token) return;
    setPlanning(sequence); setMessage(null);
    try {
      const result = await apiFetch<{ plan: VolumePlan; brief_summary: { active_foreshadowing_count: number; overdue_count: number } }>(`/projects/${projectId}/volumes/${sequence}/generate-plan`, { method: "POST" }, token);
      setEditor({ sequence, ...result, source: "ai" });
    } catch (err) { setMessage(err instanceof Error ? err.message : "卷纲生成失败"); }
    finally { setPlanning(null); }
  }

  async function upgradeTree() {
    if (!token) return;
    setPlanning(0); setMessage(null);
    try {
      await apiFetch(`/projects/${projectId}/volumes/upgrade-tree`, { method: "POST" }, token);
      onChange(await apiFetch<Outline[]>(`/projects/${projectId}/outlines`, {}, token));
      setMessage("旧项目已升级为多卷结构，正文和设定没有改动");
    } catch (err) { setMessage(err instanceof Error ? err.message : "升级失败"); }
    finally { setPlanning(null); }
  }

  function openVolume(volume: Outline) {
    const children = arcs.filter((arc) => arc.parent_id === volume.id).sort((a, b) => a.sequence - b.sequence);
    const range = volume.content.chapter_range as number[] | undefined;
    setEditor({
      sequence: volume.sequence,
      source: "saved",
      plan: {
        title: volume.title,
        goal: String(volume.content.goal ?? ""),
        opening: String(volume.content.opening ?? ""),
        turning_points: Array.isArray(volume.content.turning_points) ? volume.content.turning_points.map(String) : [],
        climax: String(volume.content.climax ?? ""),
        ending_hook: String(volume.content.ending_hook ?? ""),
        suggested_chapters: Number(volume.content.suggested_chapters ?? (range ? range[1] - range[0] + 1 : 0)),
        foreshadowing_to_resolve: Array.isArray(volume.content.foreshadowing_to_resolve) ? volume.content.foreshadowing_to_resolve.map(String) : [],
        arcs: children.map((arc) => ({ sequence: arc.sequence, title: arc.title, goal: String(arc.content.goal ?? ""), conflict: String(arc.content.conflict ?? ""), climax: String(arc.content.climax ?? ""), resolution: String(arc.content.resolution ?? ""), estimated_chapters: Number(arc.content.estimated_chapters ?? 5), involved_characters: Array.isArray(arc.content.involved_characters) ? arc.content.involved_characters.map(String) : [] })),
      },
    });
    setMessage(null);
  }

  async function savePlan() {
    if (!token || !editor) return;
    setPlanning(editor.sequence); setMessage(null);
    try {
      const payload = { ...editor.plan, turning_points: editor.plan.arcs.map((arc) => arc.goal || arc.title) };
      await apiFetch(`/projects/${projectId}/volumes/${editor.sequence}/adopt-plan`, { method: "POST", body: JSON.stringify(payload) }, token);
      const fresh = await apiFetch<Outline[]>(`/projects/${projectId}/outlines`, {}, token);
      onChange(fresh); setEditor(null); setMessage("本卷故事点已保存，后续章纲会以它为方向");
    } catch (err) { setMessage(err instanceof Error ? err.message : "保存卷纲失败"); }
    finally { setPlanning(null); }
  }

  return <div className="space-y-4">
    {volumes.length <= 1 ? <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#b88937]/35 bg-[#fff9ec] p-4"><div><strong className="text-sm">这是旧版单卷项目</strong><p className="mt-1 text-xs text-[#756348]">一键拆成多卷锚点，正文、人物和已有章纲都不会被修改。</p></div><button className="primary-button" type="button" onClick={upgradeTree} disabled={planning !== null}>{planning === 0 ? <LoaderCircle className="animate-spin" size={15} /> : <GitBranch size={15} />}升级为长篇多卷结构</button></div> : null}
    {book ? <div className="rounded-lg border border-[#a63f2f]/20 bg-[#fff8f3] p-5">
      <div className="text-xs font-semibold text-[#a63f2f]">全书蓝图</div>
      <h3 className="mt-1 font-editorial text-2xl font-bold">{book.title}</h3>
      <p className="mt-2 text-sm text-[#6e6a62]">目标 {String(book.content.target_words ?? "-")} 字 · 预计 {String(book.content.total_chapters ?? "-")} 章 · {String(book.content.volume_count ?? volumes.length)} 卷</p>
    </div> : null}
    <div className="relative space-y-3 before:absolute before:bottom-5 before:left-6 before:top-5 before:w-px before:bg-[#d2c4b2]">
      {volumes.map((volume) => {
        const children = arcs.filter((arc) => arc.parent_id === volume.id).sort((a, b) => a.sequence - b.sequence);
        const range = volume.content.chapter_range as number[] | undefined;
        const isAnchor = volume.content.status === "anchor";
        return <article key={volume.id} className="relative ml-12 cursor-pointer rounded-lg border border-black/10 bg-[#fbfaf6] p-5 shadow-[0_8px_26px_rgba(45,39,30,0.05)] transition hover:border-[#a63f2f]/35" role="button" tabIndex={0} onClick={() => openVolume(volume)} onKeyDown={(event) => { if (event.key === "Enter") openVolume(volume); }}>
          <span className={`absolute -left-[38px] top-5 flex h-7 w-7 items-center justify-center rounded-full border-2 bg-[#f3efe6] text-xs font-bold ${isAnchor ? "border-[#b9ac9b] text-[#80776c]" : "border-[#a63f2f] text-[#a63f2f]"}`}>{volume.sequence}</span>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><div className="text-[11px] font-semibold text-[#8b8174]">{range ? `第 ${range[0]}—${range[1]} 章` : "章节待定"} · {children.length ? `${children.length} 个故事点` : "故事点待定"}</div><h3 className="mt-1 font-editorial text-xl font-bold">{volume.title}</h3><p className="mt-2 text-sm leading-6 text-[#62645e]">{String(volume.content.goal ?? "点击进入，自己写或让 AI 帮你规划")}</p></div>
            <span className="flex items-center gap-1 text-xs font-semibold text-[#a63f2f]">进入本卷<ChevronRight size={15} /></span>
          </div>
        </article>;
      })}
    </div>
    {editor ? <VolumePlanEditor editor={editor} planning={planning} onChange={setEditor} onGenerate={() => generatePlan(editor.sequence)} onSave={savePlan} onClose={() => setEditor(null)} /> : null}
    {message ? <div className="rounded-md border border-[#d8d0c2] bg-white px-4 py-3 text-sm">{message}</div> : null}
  </div>;
}

function VolumePlanEditor({ editor, planning, onChange, onGenerate, onSave, onClose }: {
  editor: { sequence: number; plan: VolumePlan; source: "saved" | "ai"; brief_summary?: { active_foreshadowing_count: number; overdue_count: number } };
  planning: number | null;
  onChange: (value: { sequence: number; plan: VolumePlan; source: "saved" | "ai"; brief_summary?: { active_foreshadowing_count: number; overdue_count: number } }) => void;
  onGenerate: () => void;
  onSave: () => void;
  onClose: () => void;
}) {
  const plan = editor.plan;
  const setPlan = (next: VolumePlan) => onChange({ ...editor, plan: next });
  const updateArc = (index: number, patch: Partial<VolumePlan["arcs"][number]>) => setPlan({ ...plan, arcs: plan.arcs.map((arc, arcIndex) => arcIndex === index ? { ...arc, ...patch } : arc) });
  const addArc = () => setPlan({ ...plan, arcs: [...plan.arcs, { sequence: plan.arcs.length + 1, title: `故事点 ${plan.arcs.length + 1}`, goal: "", conflict: "", climax: "", resolution: "", estimated_chapters: 5, involved_characters: [] }] });
  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-3 sm:p-6" role="dialog" aria-modal="true" aria-label={`第${editor.sequence}卷故事点`}>
    <div className="flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-md bg-[#f8f5ee] shadow-2xl">
      <header className="flex items-center justify-between border-b border-[#d8d0c2] px-5 py-4"><div><div className="text-xs font-semibold text-[#a63f2f]">第 {editor.sequence} 卷 · {editor.source === "ai" ? "AI 草案，可直接修改" : "作者卷纲"}</div><h3 className="mt-1 font-editorial text-xl font-bold">本卷故事点</h3></div><button className="icon-button" type="button" onClick={onClose} title="关闭" aria-label="关闭"><X size={18} /></button></header>
      <div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-5 sm:px-7">
        <div className="grid gap-5 md:grid-cols-2"><label className="form-label">卷名<input className="field mt-2 h-11 px-3 font-normal" value={plan.title} onChange={(event) => setPlan({ ...plan, title: event.target.value })} /></label><label className="form-label">本卷让读者期待什么<input className="field mt-2 h-11 px-3 font-normal" value={plan.goal} onChange={(event) => setPlan({ ...plan, goal: event.target.value })} /></label><label className="form-label">本卷从什么局面开始<textarea className="field mt-2 min-h-20 p-3 font-normal" value={plan.opening ?? ""} onChange={(event) => setPlan({ ...plan, opening: event.target.value })} /></label><label className="form-label">卷末局面发生什么变化<textarea className="field mt-2 min-h-20 p-3 font-normal" value={plan.ending_hook ?? ""} onChange={(event) => setPlan({ ...plan, ending_hook: event.target.value })} /></label></div>
        <div className="mt-7 flex flex-wrap items-center justify-between gap-3 border-t border-[#d8d0c2] pt-5"><div><h4 className="font-editorial text-lg font-bold">故事点</h4><p className="mt-1 text-xs text-[#74756e]">每个故事点是一段连续推进，不需要提前拆成几十章。</p></div><button className="secondary-button" type="button" onClick={addArc}><Plus size={15} />添加故事点</button></div>
        <div className="mt-4 divide-y divide-[#ded8cd] border-y border-[#ded8cd]">{plan.arcs.length ? plan.arcs.map((arc, index) => <section className="py-5" key={index}><div className="flex items-center justify-between gap-3"><strong className="text-sm">故事点 {index + 1}</strong><button className="icon-button h-8 w-8" type="button" title="删除故事点" onClick={() => setPlan({ ...plan, arcs: plan.arcs.filter((_, itemIndex) => itemIndex !== index).map((item, itemIndex) => ({ ...item, sequence: itemIndex + 1 })) })}><Trash2 size={14} /></button></div><div className="mt-3 grid gap-4 md:grid-cols-2"><label className="form-label">名称<input className="field mt-2 h-10 px-3 font-normal" value={arc.title} onChange={(event) => updateArc(index, { title: event.target.value })} /></label><label className="form-label">这一段要让什么改变<input className="field mt-2 h-10 px-3 font-normal" value={arc.goal} onChange={(event) => updateArc(index, { goal: event.target.value })} /></label><label className="form-label">人物遇到什么阻力<textarea className="field mt-2 min-h-20 p-3 font-normal" value={arc.conflict} onChange={(event) => updateArc(index, { conflict: event.target.value })} /></label><label className="form-label">最后付出什么、留下什么<textarea className="field mt-2 min-h-20 p-3 font-normal" value={arc.resolution} onChange={(event) => updateArc(index, { resolution: event.target.value })} /></label></div></section>) : <div className="py-8 text-center text-sm text-[#85857d]">还没有故事点。可以自己添加，也可以让 AI 先给一版。</div>}</div>
        {editor.brief_summary ? <p className="mt-4 text-xs text-[#786e60]">规划时参考了 {editor.brief_summary.active_foreshadowing_count} 条活跃伏笔，其中 {editor.brief_summary.overdue_count} 条已临期。</p> : null}
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[#d8d0c2] bg-white/55 px-5 py-4"><button className="secondary-button" type="button" disabled={planning !== null} onClick={onGenerate}>{planning === editor.sequence ? <LoaderCircle className="animate-spin" size={15} /> : <Sparkles size={15} />}{editor.source === "ai" ? "让 AI 换一版" : "让 AI 帮我规划"}</button><div className="flex gap-2"><button className="secondary-button" type="button" onClick={onClose}>取消</button><button className="primary-button" type="button" disabled={planning !== null || !plan.title.trim() || !plan.goal.trim()} onClick={onSave}><Save size={15} />保存本卷</button></div></footer>
    </div>
  </div>;
}

function ContentView({ content }: { content: Record<string, unknown> }) {
  return (
    <div className="mt-4 grid gap-2 text-sm leading-7 text-[#656760]">
      {Object.entries(content).slice(0, 6).map(([key, value]) => (
        <div key={key} className="grid gap-1 border-t border-[#e3ddd2] pt-2 sm:grid-cols-[120px_minmax(0,1fr)]">
          <span className="text-xs font-semibold text-[#8b8174]">{key}</span>
          <span className="whitespace-pre-wrap break-words">{typeof value === "string" ? value : JSON.stringify(value, null, 2)}</span>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex min-h-72 flex-col items-center justify-center rounded-lg border border-dashed border-[#bfb5a7] bg-white/35 px-6 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[#ebe5da] text-[#7b7c75]"><BookOpenText size={21} /></span>
      <p className="mt-4 text-sm text-[#7b7c75]">{text}</p>
    </div>
  );
}
