"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getSupabase } from "@/lib/supabase";
import { apiBaseUrl } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

type Word = {
  id: string;
  text: string;
  start: number;
  end: number;
  speaker: string | null;
  final: boolean;
};

type RefinedTurn = {
  start: number;
  end: number;
  speaker: string | null;
  text: string;
  used_entity_ids: string[];
};

type Status = "idle" | "connecting" | "listening" | "stopped" | "error";

const PALETTE = ["bg-blue-50", "bg-amber-50", "bg-emerald-50", "bg-rose-50", "bg-violet-50"];
function speakerClass(map: Map<string, number>, spk: string | null): string {
  if (!spk) return "";
  if (!map.has(spk)) map.set(spk, map.size);
  return PALETTE[map.get(spk)! % PALETTE.length];
}

function wordKey(w: { start: number; end: number }) {
  return `${w.start.toFixed(3)}:${w.end.toFixed(3)}`;
}

export default function LivePage() {
  const { active } = useTenant();
  const [status, setStatus] = useState<Status>("idle");
  const [err, setErr] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [lang, setLang] = useState("");
  const [speakers, setSpeakers] = useState("");

  const [wordsMap, setWordsMap] = useState<Map<string, Word>>(new Map());
  const [refinedTurns, setRefinedTurns] = useState<RefinedTurn[]>([]);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const channelRef = useRef<RTCDataChannel | null>(null);

  const reset = () => {
    setWordsMap(new Map());
    setRefinedTurns([]);
    setSessionId(null);
    setErr(null);
  };

  const handleEvent = useCallback((ev: any) => {
    if (ev.type === "session_started") {
      setSessionId(ev.session_id);
    } else if (ev.type === "words_upserted") {
      setWordsMap((prev) => {
        const next = new Map(prev);
        for (const k of [...next.keys()]) {
          const w = next.get(k)!;
          const mid = (w.start + w.end) / 2;
          if (mid >= ev.window_start && mid < ev.window_end && !w.final) {
            next.delete(k);
          }
        }
        for (const w of ev.words) {
          const existing = next.get(wordKey(w));
          next.set(wordKey(w), {
            id: wordKey(w),
            text: w.text,
            start: w.start,
            end: w.end,
            speaker: existing?.speaker ?? w.speaker ?? null,
            final: existing?.final ?? false,
          });
        }
        return next;
      });
    } else if (ev.type === "speakers_updated") {
      setWordsMap((prev) => {
        const next = new Map<string, Word>();
        for (const [k, w] of prev) {
          const mid = (w.start + w.end) / 2;
          let speaker = w.speaker;
          for (const s of ev.segments) {
            if (s.start <= mid && mid < s.end) {
              speaker = s.speaker;
              break;
            }
          }
          next.set(k, { ...w, speaker });
        }
        return next;
      });
    } else if (ev.type === "segment_finalized") {
      setWordsMap((prev) => {
        const next = new Map<string, Word>();
        for (const [k, w] of prev) {
          next.set(k, { ...w, final: w.end <= ev.end ? true : w.final });
        }
        return next;
      });
    } else if (ev.type === "segment_refined") {
      setRefinedTurns((prev) => {
        const kept = prev.filter((t) => t.end <= ev.start);
        const combined = [...kept, ...ev.turns];
        combined.sort((a, b) => a.start - b.start);
        return combined;
      });
    } else if (ev.type === "session_ended") {
      setStatus("stopped");
    }
  }, []);

  const stop = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    channelRef.current = null;
    setStatus("stopped");
  }, []);

  const start = useCallback(async () => {
    if (!active) return;
    reset();
    setStatus("connecting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: false,
      });
      streamRef.current = stream;

      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      const dc = pc.createDataChannel("events");
      channelRef.current = dc;
      dc.onmessage = (e) => {
        try {
          handleEvent(JSON.parse(e.data));
        } catch (err) {
          console.error("bad event payload", err, e.data);
        }
      };
      for (const track of stream.getAudioTracks()) pc.addTrack(track, stream);

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const { data: { session } } = await getSupabase().auth.getSession();
      const params = new URLSearchParams({ tenant: active.id });
      if (lang.trim()) params.set("lang", lang.trim());
      if (speakers.trim()) params.set("speakers", speakers.trim());

      const resp = await fetch(`${apiBaseUrl()}/offer?${params}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.access_token ?? ""}`,
        },
        body: JSON.stringify({
          sdp: pc.localDescription?.sdp,
          type: pc.localDescription?.type,
        }),
      });
      if (!resp.ok) throw new Error(`offer failed: ${resp.status} ${await resp.text()}`);
      const answer = await resp.json();
      await pc.setRemoteDescription(answer);
      setStatus("listening");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setStatus("error");
      stop();
    }
  }, [active, handleEvent, lang, speakers, stop]);

  useEffect(() => {
    return () => {
      if (pcRef.current) pcRef.current.close();
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const sortedWords = useMemo(
    () => [...wordsMap.values()].sort((a, b) => a.start - b.start),
    [wordsMap],
  );
  const speakerMap = new Map<string, number>();

  if (!active) {
    return <p className="text-gray-500">Select a workspace to start a session.</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Live transcription</h1>

      <div className="flex flex-wrap items-center gap-3 bg-white border border-gray-200 rounded p-3">
        <button
          type="button"
          onClick={start}
          disabled={status === "connecting" || status === "listening"}
          className="bg-blue-600 text-white text-sm rounded px-3 py-1 disabled:opacity-60"
        >
          {status === "listening" ? "Listening…" : "Start"}
        </button>
        <button
          type="button"
          onClick={stop}
          disabled={status !== "listening"}
          className="bg-gray-200 text-gray-800 text-sm rounded px-3 py-1 disabled:opacity-60"
        >
          Stop
        </button>
        <label className="text-sm text-gray-700 flex items-center gap-1">
          Language
          <input
            type="text"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            placeholder="auto"
            className="ml-1 w-16 border border-gray-300 rounded px-2 py-0.5 text-sm"
          />
        </label>
        <label className="text-sm text-gray-700 flex items-center gap-1">
          Speakers
          <input
            type="number"
            min={1}
            max={8}
            value={speakers}
            onChange={(e) => setSpeakers(e.target.value)}
            placeholder="auto"
            className="ml-1 w-16 border border-gray-300 rounded px-2 py-0.5 text-sm"
          />
        </label>
        <span className="text-sm text-gray-500 ml-auto">
          {status === "idle"
            ? "idle"
            : status === "connecting"
            ? "connecting…"
            : status === "listening"
            ? `listening · ${sessionId?.slice(0, 8) ?? ""}`
            : status === "stopped"
            ? "stopped"
            : "error"}
        </span>
      </div>

      {err ? <p className="text-sm text-red-600">{err}</p> : null}

      <section className="grid md:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded p-4 min-h-48">
          <h2 className="text-sm font-medium text-gray-700 mb-2">Raw (live)</h2>
          <div className="text-sm leading-relaxed whitespace-pre-wrap">
            {sortedWords.map((w) => (
              <span
                key={w.id}
                className={`inline-block px-0.5 rounded ${
                  w.final ? "text-gray-900" : "text-gray-400"
                } ${speakerClass(speakerMap, w.speaker)}`}
                title={`${w.start.toFixed(2)}–${w.end.toFixed(2)}s${
                  w.speaker ? ` · ${w.speaker}` : ""
                }`}
              >
                {w.text}{" "}
              </span>
            ))}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded p-4 min-h-48">
          <h2 className="text-sm font-medium text-gray-700 mb-2">
            Refined (LLM + graph)
          </h2>
          <div className="space-y-2">
            {refinedTurns.map((t, i) => (
              <div
                key={i}
                className={`rounded px-2 py-1 text-sm ${speakerClass(
                  speakerMap,
                  t.speaker,
                )}`}
              >
                <span className="text-xs font-medium text-gray-600 mr-2">
                  {t.speaker ?? "?"}:
                </span>
                {t.text}
                {t.used_entity_ids.length > 0 && (
                  <span className="ml-2 text-xs text-gray-500">
                    [{t.used_entity_ids.join(", ")}]
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
