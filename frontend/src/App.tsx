import { useEffect, useRef, useState } from "react";
import { PromptInput } from "@/components/ui/ai-chat-input";
import { ask, type Source, type Usage } from "@/api";
import { cn } from "@/lib/utils";

type Turn =
  | { role: "user"; text: string }
  | { role: "answer"; text: string; sources: Source[]; usage?: Usage }
  | { role: "error"; text: string };

const EXAMPLES = [
  "How many points did SGA score on 4/8?",
  "Who won the Knicks vs Spurs game on Christmas 2024?",
  "Who dropped 40+ points for the Lakers this season?",
  "Who led the league in assists per game in 2025-26?",
];

const CITATION = /\s*\[((?:line|game):[\w:]+)\]/g;

function CourtLines() {
  // A half-court, drawn as the floor's painted lines.
  return (
    <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1200 120" preserveAspectRatio="xMaxYMid slice" aria-hidden="true">
      <defs>
        <pattern id="planks" width="160" height="14" patternUnits="userSpaceOnUse">
          <rect width="160" height="14" fill="var(--maple)" />
          <path d="M0 13.5h160M70 0v14" stroke="var(--maple-dark)" strokeOpacity=".35" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width="1200" height="120" fill="url(#planks)" />
      <g fill="none" stroke="#fff" strokeOpacity=".8" strokeWidth="3">
        <line x1="600" y1="0" x2="600" y2="120" />
        <circle cx="600" cy="60" r="46" />
        <circle cx="600" cy="60" r="14" />
        <path d="M0 18h150a42 42 0 0 1 0 84H0" />
        <path d="M1200 18h-150a42 42 0 0 0 0 84h150" />
      </g>
    </svg>
  );
}

function Answer({ turn }: { turn: Extract<Turn, { role: "answer" }> }) {
  const [open, setOpen] = useState(false);
  const order = turn.sources.map((s) => s.id);
  const parts = turn.text.split(CITATION);
  return (
    <div className="max-w-[68ch] animate-in fade-in slide-in-from-bottom-1 duration-300">
      <p className="whitespace-pre-line text-[17px] leading-[1.6]">
        {parts.map((part, i) => {
          if (i % 2 === 0) return <span key={i}>{part}</span>;
          const n = order.indexOf(part) + 1;
          return n > 0 ? (
            <button
              key={i}
              type="button"
              onClick={() => setOpen(true)}
              className="ml-1 inline-flex size-5 -translate-y-0.5 items-center justify-center rounded-full bg-secondary align-middle text-[11px] font-semibold text-paint hover:bg-accent"
              aria-label={`Show source ${n}`}
            >
              {n}
            </button>
          ) : null;
        })}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
        {turn.sources.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="font-semibold text-paint underline-offset-4 hover:underline"
          >
            {open ? "Hide" : "Show"} {turn.sources.length === 1 ? "the source" : `${turn.sources.length} sources`}
          </button>
        )}
        {turn.usage && (
          <span>
            Answered in {(turn.usage.latency_ms / 1000).toFixed(1)} s from{" "}
            {turn.usage.tools.includes("search_records") ? "box-score passages" : "season totals"}
            {turn.usage.cost_usd != null && `, $${turn.usage.cost_usd.toFixed(4)}`}
          </span>
        )}
      </div>
      {open && (
        <ol className="mt-3 space-y-2 animate-in fade-in slide-in-from-top-1 duration-200">
          {turn.sources.map((s, i) => (
            <li key={s.id} className="flex gap-3 rounded-lg border bg-card p-3 text-[14px] leading-relaxed">
              <span className="font-display text-lg font-semibold leading-none text-maple-dark dark:text-maple">{i + 1}</span>
              <span>{s.text}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function App() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, loading]);

  const send = async (question: string) => {
    const q = question.trim();
    if (!q || loading) return;
    setTurns((t) => [...t, { role: "user", text: q }]);
    setLoading(true);
    try {
      const r = await ask(q);
      setTurns((t) => [...t, { role: "answer", text: r.answer, sources: r.sources ?? [], usage: r.usage }]);
    } catch {
      setTurns((t) => [...t, { role: "error", text: "Couldn't reach the stats service. Check your connection and ask again." }]);
    } finally {
      setLoading(false);
    }
  };

  const empty = turns.length === 0;

  return (
    <div className="flex h-full flex-col">
      <header className="relative h-[88px] shrink-0 overflow-hidden sm:h-[104px]">
        <CourtLines />
        <div className="relative mx-auto flex h-full max-w-3xl items-center px-5">
          <h1 className="font-display text-[44px] font-extrabold italic leading-none tracking-tight text-white drop-shadow-[0_2px_0_var(--maple-dark)] sm:text-[52px]">
            Courtside
          </h1>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        <div className={cn("mx-auto max-w-3xl px-5 pb-40", empty ? "pt-14 sm:pt-20" : "pt-8")}>
          {empty ? (
            <section className="animate-in fade-in slide-in-from-bottom-2 duration-500">
              <h2 className="font-display text-[44px] font-extrabold leading-[0.95] tracking-tight sm:text-[64px]">
                Ask the box score.
              </h2>
              <p className="mt-4 max-w-[56ch] text-[17px] leading-relaxed text-muted-foreground">
                Every NBA regular-season game and player line since the 2023-24 season. Each answer cites the box scores it came from.
              </p>
              <div className="mt-8 flex flex-wrap gap-2">
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => send(q)}
                    className="rounded-full border bg-card px-4 py-2 text-left text-[15px] hover:border-maple hover:bg-accent"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="space-y-8">
              {turns.map((t, i) =>
                t.role === "user" ? (
                  <p key={i} className="font-display text-[26px] font-semibold leading-tight tracking-tight">
                    {t.text}
                  </p>
                ) : t.role === "answer" ? (
                  <Answer key={i} turn={t} />
                ) : (
                  <p key={i} className="text-[16px] text-destructive">{t.text}</p>
                ),
              )}
              {loading && (
                <p className="text-[15px] text-muted-foreground" role="status">
                  Reading the box scores…
                </p>
              )}
            </div>
          )}
          <div ref={endRef} />
        </div>
      </main>

      <div className="pointer-events-none fixed inset-x-0 bottom-0 bg-gradient-to-t from-background via-background/90 to-transparent pb-6 pt-10">
        <div className="pointer-events-auto mx-auto flex max-w-3xl justify-center px-5">
          <PromptInput
            onSubmit={(value) => send(value)}
            placeholder="Ask about a game or player"
            showModelSelector={false}
            showEffort={false}
            allowAttachments={false}
            disabled={loading}
            collapsedWidth={420}
            expandedWidth={680}
          />
        </div>
      </div>
    </div>
  );
}
