import { useState, useRef, useEffect } from "react";
import { submitResearch, openStream } from "../api";

const STAGES = [
  { id: "planner",     label: "Planner" },
  { id: "retriever",   label: "Retriever" },
  { id: "evaluator",   label: "Evaluator" },
  { id: "synthesizer", label: "Synthesizer" },
  { id: "formatter",   label: "Formatter" },
];

const CHAR_SPEED_MS = 12;

export default function ResearchForm() {
  const [question, setQuestion]   = useState("");
  const [mode, setMode]           = useState("standard");
  const [running, setRunning]     = useState(false);
  const [activeStage, setActive]  = useState(null);
  const [doneStages, setDone]     = useState(new Set());
  const [outputUrl, setOutputUrl] = useState(null);
  const [error, setError]         = useState(null);

  // Typewriter state
  const [displayed, setDisplayed] = useState("");
  const typeQueueRef  = useRef([]);   // strings waiting to be typed
  const charBufRef    = useRef("");   // string currently being typed
  const charIdxRef    = useRef(0);
  const intervalRef   = useRef(null);
  const esRef         = useRef(null);
  const logEndRef     = useRef(null);

  // Start the typewriter interval once on mount
  useEffect(() => {
    intervalRef.current = setInterval(() => {
      if (charIdxRef.current < charBufRef.current.length) {
        const ch = charBufRef.current[charIdxRef.current++];
        setDisplayed(prev => prev + ch);
      } else if (typeQueueRef.current.length > 0) {
        charBufRef.current = typeQueueRef.current.shift();
        charIdxRef.current = 0;
      }
    }, CHAR_SPEED_MS);
    return () => clearInterval(intervalRef.current);
  }, []);

  // Auto-scroll the log to bottom
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayed]);

  function enqueue(text) {
    typeQueueRef.current.push(text);
  }

  function reset() {
    esRef.current?.close();
    setRunning(false);
    setActive(null);
    setDone(new Set());
    setOutputUrl(null);
    setError(null);
    setDisplayed("");
    typeQueueRef.current = [];
    charBufRef.current = "";
    charIdxRef.current = 0;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (question.trim().length < 10 || running) return;

    reset();
    setRunning(true);

    let jobId;
    try {
      const data = await submitResearch(question, mode);
      jobId = data.job_id;
    } catch (err) {
      setError(err.message);
      setRunning(false);
      return;
    }

    const es = openStream(jobId);
    esRef.current = es;

    es.onmessage = (e) => {
      const event = JSON.parse(e.data);

      if (event.type === "stage_start") {
        setActive(event.stage);
        enqueue("\n" + event.message);
      }

      if (event.type === "progress") {
        enqueue("\n" + event.message);
      }

      if (event.type === "stage_done") {
        setDone(prev => new Set([...prev, event.stage]));
        enqueue("\n" + event.message + "\n");
      }

      if (event.type === "done") {
        setActive(null);
        setDone(new Set(STAGES.map(s => s.id)));
        enqueue("\n✓ Your report is ready!\n");
        setOutputUrl(event.output_url);
        setRunning(false);
        es.close();
      }

      if (event.type === "error") {
        setError(event.error);
        setRunning(false);
        setActive(null);
        es.close();
      }
    };

    es.onerror = () => {
      if (running) {
        setError("Connection lost. Refresh and try again.");
        setRunning(false);
      }
      es.close();
    };
  }

  return (
    <div className="max-w-2xl mx-auto p-6 flex flex-col gap-6">
      {/* Input form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium text-gray-700">Research Question</span>
          <textarea
            className="border border-gray-300 rounded-md p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={3}
            minLength={10}
            maxLength={500}
            placeholder="Enter your research question (min 10 characters)…"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            disabled={running}
          />
        </label>

        <div className="flex gap-3 items-end">
          <label className="flex flex-col gap-1 flex-1">
            <span className="text-sm font-medium text-gray-700">Mode</span>
            <select
              className="border border-gray-300 rounded-md p-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={mode}
              onChange={e => setMode(e.target.value)}
              disabled={running}
            >
              <option value="quick">Quick (1 pass)</option>
              <option value="standard">Standard (2 passes)</option>
              <option value="deep">Deep (3 passes)</option>
            </select>
          </label>

          <button
            type="submit"
            disabled={running || question.trim().length < 10}
            className="bg-blue-600 text-white rounded-md py-2 px-5 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {running ? "Running…" : "Research"}
          </button>
        </div>
      </form>

      {/* Stage progress badges */}
      {(running || outputUrl || error) && (
        <div className="flex flex-wrap gap-2">
          {STAGES.map((stage, i) => {
            const isDone   = doneStages.has(stage.id);
            const isActive = activeStage === stage.id;
            return (
              <div key={stage.id} className="flex items-center gap-1">
                <span className={`
                  inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium
                  ${isDone   ? "bg-green-100 text-green-700" :
                    isActive ? "bg-blue-100 text-blue-700"   :
                               "bg-gray-100 text-gray-400"}
                `}>
                  {isDone ? (
                    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/>
                    </svg>
                  ) : isActive ? (
                    <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse inline-block" />
                  ) : (
                    <span className="w-2.5 h-2.5 rounded-full bg-gray-300 inline-block" />
                  )}
                  {stage.label}
                </span>
                {i < STAGES.length - 1 && (
                  <span className="text-gray-300 text-xs">→</span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Typewriter log */}
      {(running || displayed) && (
        <div className="bg-gray-950 rounded-lg p-4 font-mono text-sm text-green-400 min-h-32 max-h-80 overflow-y-auto whitespace-pre-wrap">
          {displayed}
          {running && (
            <span className="inline-block w-2 h-4 bg-green-400 ml-0.5 animate-pulse" />
          )}
          <div ref={logEndRef} />
        </div>
      )}

      {/* Download */}
      {outputUrl && (
        <a
          href={outputUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-block self-start bg-green-600 text-white rounded-md py-2 px-5 text-sm font-medium hover:bg-green-700 transition-colors"
        >
          Download Report
        </a>
      )}

      {/* Error */}
      {error && (
        <p className="text-sm text-red-600 font-medium">{error}</p>
      )}
    </div>
  );
}
