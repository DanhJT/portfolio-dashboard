import React, { useState } from "react";
import { generateCommentary } from "../api.js";

function Spinner() {
  return (
    <span
      className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-neutral-600 border-t-white"
      aria-label="loading"
    />
  );
}

export default function CommentaryButton({ metrics, module = "overview", label = "Generate AI Commentary" }) {
  const [commentary, setCommentary] = useState(null);
  const [generatedAt, setGeneratedAt] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function onClick() {
    if (!metrics) return;
    setLoading(true);
    setError(null);
    try {
      const res = await generateCommentary(metrics, module);
      setCommentary(res.commentary);
      setGeneratedAt(res.generated_at);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm uppercase tracking-wider text-neutral-400">
          AI Commentary
        </h3>
        {generatedAt && (
          <span className="text-xs text-neutral-500 font-mono">
            {new Date(generatedAt).toLocaleTimeString()}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onClick}
        disabled={loading || !metrics}
        className="inline-flex items-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-xs font-medium text-black hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading && <Spinner />}
        {loading ? "Generating…" : label}
      </button>
      {error && (
        <div className="mt-3 rounded-md border border-rose-900 bg-rose-950/50 p-2 text-xs text-rose-300">
          {error}
        </div>
      )}
      {commentary && !error && (
        <div className="mt-3 rounded-md border border-neutral-800 bg-black p-3 text-sm leading-relaxed text-neutral-200 whitespace-pre-wrap">
          {commentary}
        </div>
      )}
    </div>
  );
}
