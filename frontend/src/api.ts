export interface Source {
  id: string;
  text: string;
}

export interface Usage {
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  tools: string[];
}

export interface ChatResponse {
  answer: string;
  evidence: { table: string; id: string }[];
  sources?: Source[];
  usage?: Usage;
}

export async function ask(question: string, signal?: AbortSignal): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!res.ok) throw new Error(`The stats service returned ${res.status}.`);
  return res.json();
}
