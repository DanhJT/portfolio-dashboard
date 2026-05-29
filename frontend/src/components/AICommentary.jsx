import React, { useState } from "react";
import { generateCommentary } from "../api.js";

function Spinner() {
  return (
    <span
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-neutral-600 border-t-white"
      aria-label="loading"
    />
  );
}

function formatTimestamp(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function AICommentary({ metrics }) {
  const [commentary, setCommentary] = useState(null);
  const [generatedAt, setGeneratedAt] = useState(null);
  const [model, setModel] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function onGenerate() {
    if (!metrics) return;
    setLoading(true);
    setError(null);
    try {
      const res = await generateCommentary(metrics);
      setCommentary(res.commentary);
      setGeneratedAt(res.generated_at);
      setModel(res.model);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card flex flex-col">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm uppercase tracking-wider text-neutral-400">
          AI Commentary
        </h2>
        {generatedAt && (
          <span className="text-xs text-neutral-500">
            {formatTimestamp(generatedAt)}
          </span>
        )}
      </div>

      <button
        type="button"
        onClick={onGenerate}
        disabled={loading || !metrics}
        className="self-start mb-4 inline-flex items-center gap-2 rounded-md bg-white px-3 py-1.5 text-sm font-medium text-black hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading && <Spinner />}
        {loading ? "Generating…" : "Generate AI Commentary"}
      </button>

      {error && (
        <div className="rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {commentary && !error && (
        <div className="rounded-md border border-neutral-800 bg-black p-4 text-sm leading-relaxed text-neutral-200 whitespace-pre-wrap">
          {commentary}
          {model && (
            <div className="mt-3 text-xs font-mono text-neutral-500">
              {model}
            </div>
          )}
        </div>
      )}

      {!commentary && !error && !loading && (
        <div className="text-sm text-neutral-500">
          Click the button to ask for a senior-analyst read on the current risk
          profile.
        </div>
      )}
    </div>
  );
}
