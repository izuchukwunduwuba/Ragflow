import { useRef, useState } from "react";
import CanonicalDataCard from "./CanonicalDataCard";

const ACCEPTED_TYPES: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
  "text/plain": "TXT",
  "text/csv": "CSV",
  "application/json": "JSON",
  "text/markdown": "MD",
  "text/x-markdown": "MD",
};

type UploadState =
  | { status: "idle" }
  | { status: "uploading" }
  | { status: "processing" }
  | { status: "complete"; fileName: string; result: unknown }
  | { status: "error"; message: string };

export default function DocumentUpload() {
  const [state, setState] = useState<UploadState>({ status: "idle" });
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    if (!ACCEPTED_TYPES[file.type]) {
      setState({ status: "error", message: `File type not supported. Accepted: ${Object.values(ACCEPTED_TYPES).join(", ")}` });
      return;
    }

    setState({ status: "uploading" });

    try {
      const formData = new FormData();
      formData.append("file", file);

      setState({ status: "processing" });

      const res = await fetch(`${import.meta.env.VITE_API_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error ?? "Processing failed");
      }

      const result = await res.json();
      setState({ status: "complete", fileName: file.name, result });
    } catch (err) {
      setState({ status: "error", message: err instanceof Error ? err.message : "Something went wrong" });
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function reset() {
    setState({ status: "idle" });
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="min-h-screen bg-gray-50 flex justify-center p-6 pt-16">
      <div className="w-full max-w-xl">

        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold text-gray-900">Document Upload</h1>
          <p className="text-sm text-gray-500 mt-1">Upload insurance documents for processing</p>
        </div>

        {/* Upload area */}
        {state.status === "idle" && (
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
              dragOver ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:border-gray-300"
            }`}
          >
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center">
                <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700">
                  Drop your file here, or <span className="text-blue-600">browse</span>
                </p>
                <p className="text-xs text-gray-400 mt-1">PDF, DOCX, TXT, CSV, JSON, Markdown</p>
              </div>
            </div>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept={Object.keys(ACCEPTED_TYPES).join(",")}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
            />
          </div>
        )}

        {/* Uploading */}
        {state.status === "uploading" && (
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center">
                <svg className="w-6 h-6 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              </div>
              <p className="text-sm text-gray-500">Uploading...</p>
            </div>
          </div>
        )}

        {/* Processing */}
        {state.status === "processing" && (
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center">
                <svg className="w-6 h-6 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">Processing document</p>
                <p className="text-xs text-gray-400 mt-1">Converting, chunking and extracting canonical data...</p>
              </div>
            </div>
          </div>
        )}

        {/* Complete */}
        {state.status === "complete" && (
          <>
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-green-50 flex items-center justify-center flex-shrink-0">
                  <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{state.fileName}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {(state.result as { chunk_count: number }).chunk_count} chunks extracted
                  </p>
                </div>
                <button onClick={reset} className="text-xs text-blue-600 hover:text-blue-700 font-medium flex-shrink-0">
                  Upload another
                </button>
              </div>
            </div>

            <CanonicalDataCard
              data={(state.result as { canonical: Parameters<typeof CanonicalDataCard>[0]["data"] }).canonical}
            />
          </>
        )}

        {/* Error */}
        {state.status === "error" && (
          <div className="bg-white rounded-xl border border-red-100 p-8">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center">
                <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">Something went wrong</p>
                <p className="text-sm text-gray-500 mt-0.5">{state.message}</p>
              </div>
              <button onClick={reset} className="text-sm text-blue-600 hover:text-blue-700 font-medium">
                Try again
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
