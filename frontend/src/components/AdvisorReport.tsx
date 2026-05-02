import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  report: string;
  downloadName?: string;
}

export default function AdvisorReport({ report, downloadName = "reporte_asesor.md" }: Props) {
  const handleDownload = () => {
    const blob = new Blob([report], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = downloadName;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="border border-gray-700 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 bg-gray-900 border-b border-gray-700">
        <span className="text-sm font-medium text-gray-200">Reporte del Asesor</span>
        <button
          onClick={handleDownload}
          className="text-xs text-gray-400 hover:text-white transition-colors"
        >
          ↓ Descargar .md
        </button>
      </div>

      <div className="p-6 max-h-[70vh] overflow-y-auto bg-gray-950">
        <div className="
          prose prose-invert prose-sm max-w-none
          prose-headings:text-white prose-headings:font-semibold prose-headings:border-b prose-headings:border-gray-800 prose-headings:pb-1
          prose-h1:text-xl prose-h2:text-base prose-h3:text-sm prose-h3:border-0
          prose-p:text-gray-300 prose-p:leading-relaxed
          prose-strong:text-white
          prose-em:text-gray-400
          prose-blockquote:border-l-green-500 prose-blockquote:text-gray-400 prose-blockquote:bg-gray-900 prose-blockquote:py-0.5
          prose-code:text-green-400 prose-code:bg-gray-900 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none
          prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-700
          prose-hr:border-gray-700
          prose-li:text-gray-300
          [&_table]:w-full [&_table]:border-collapse [&_table]:text-sm
          [&_thead]:bg-gray-800
          [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold [&_th]:text-gray-300 [&_th]:uppercase [&_th]:tracking-wider [&_th]:border [&_th]:border-gray-700
          [&_td]:px-3 [&_td]:py-2 [&_td]:text-gray-300 [&_td]:border [&_td]:border-gray-800
          [&_tbody_tr:nth-child(even)]:bg-gray-900/50
          [&_tbody_tr:hover]:bg-gray-800/40
        ">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
