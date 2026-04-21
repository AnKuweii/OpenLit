import React, { useMemo, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import { defaultSchema } from "hast-util-sanitize";
import { FileText, ExternalLink } from "lucide-react";
import { getCitationChunk } from "../services/api";

const API_BASE = "http://localhost:8001/api/v1";
const API_HOST = String(API_BASE).replace(/\/api\/v\d+$/, "");

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames || []), "img"],
  attributes: {
    ...(defaultSchema.attributes || {}),
    "*": [...((defaultSchema.attributes && defaultSchema.attributes["*"]) || []), "className"],
    img: [
      "src",
      "alt",
      "title",
      "loading",
      "width",
      "height",
      "className",
    ],
    a: [
      ...((defaultSchema.attributes && defaultSchema.attributes["a"]) || []),
      "target",
      "rel",
    ],
  },
  protocols: {
    ...(defaultSchema.protocols || {}),
    src: ["http", "https", "data", "blob"],
    href: ["http", "https", "mailto", "tel"],
  },
};

function toAbsoluteApiUrl(src: string) {
  if (!src) return "";
  if (src.startsWith("http://") || src.startsWith("https://")) return src;
  if (src.startsWith("/api/")) return `${API_HOST}${src}`;
  return src;
}

function Code(props: any) {
  const { inline, className, children } = props;
  const language = (className || "").replace("language-", "") || "code";
  if (inline) {
    return <code className="bg-muted/40 px-1.5 py-0.5 rounded-md text-sm" style={{ color: '#00f0ff' }}>{children}</code>;
  }
  return (
    <div className="my-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-muted-foreground/70">{language}</span>
        <button
          className="text-xs px-2 py-0.5 rounded-md bg-white/8 hover:bg-white/15 transition-colors duration-200"
          onClick={() => navigator.clipboard.writeText(String(children))}
        >
          Copy
        </button>
      </div>
      <pre className="text-sm overflow-x-auto p-3 rounded-xl" style={{ background: 'rgba(10,5,20,0.6)', border: '1px solid rgba(0,240,255,0.15)' }}>
        <code style={{ color: '#c0c0d0' }}>{children}</code>
      </pre>
    </div>
  );
}

function Img(props: React.ImgHTMLAttributes<HTMLImageElement>) {
  const fixedSrc = useMemo(() => {
    const src = String(props.src || "");
    if (!src) return "";

    if (src.startsWith("./images/") || src.startsWith("images/")) return "";

    return toAbsoluteApiUrl(src);
  }, [props.src]);

  const [err, setErr] = useState(false);
  if (!fixedSrc || err) return null;

  return (
    <img
      {...props}
      src={fixedSrc}
      onError={() => setErr(true)}
      className={"max-w-full h-auto rounded-xl border border-border/20 " + (props.className ?? "")}
      loading="lazy"
    />
  );
}

function ReferenceCard({ citationId, index }: { citationId: string; index: number }) {
  const [loading, setLoading] = useState(false);
  const [snippet, setSnippet] = useState<string>("");
  const [previewUrl, setPreviewUrl] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        const chunk = await getCitationChunk(citationId);
        if (!mounted) return;
        setSnippet(chunk?.snippet || "");
        setPreviewUrl(chunk?.previewUrl ? toAbsoluteApiUrl(chunk.previewUrl) : "");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [citationId]);

  return (
    <div className="bg-muted/15 rounded-xl p-3 border border-border/20">
      <div className="flex items-start gap-2.5">
        <span className="inline-flex items-center justify-center w-5 h-5 text-xs font-bold rounded-full shrink-0" style={{ background: 'rgba(0,240,255,0.15)', color: '#00f0ff', border: '1px solid rgba(0,240,255,0.3)' }}>
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
            {loading ? "加载中…" : (snippet ? (snippet.length > 200 ? snippet.slice(0, 200) + "…" : snippet) : "（无文本片段）")}
          </div>
          {previewUrl && (
            <button
              className="mt-2 inline-flex items-center text-xs px-2 py-0.5 rounded-md bg-white/8 hover:bg-white/15 transition-colors duration-200"
              onClick={() => window.open(previewUrl, "_blank")}
            >
              <ExternalLink className="w-3 h-3 mr-1" />
              查看原页
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export type Reference = {
  id: number;
  text?: string;
  page?: number;
  citationId?: string;
  rank?: number;
  snippet?: string;
};

export function MarkdownRenderer({
  content,
  references = [],
}: {
  content: string;
  references?: Reference[];
}) {
  const sanitizedContent = useMemo(
    () =>
      content
        .replace(/<img[\s\S]*?>/gi, "")
        .replace(/!\[[^\]]*]\(\s*(?:\.\/)?images\/[^)]+\)/gi, ""),
    [content]
  );

  return (
    <div className="space-y-2.5 text-foreground leading-relaxed prose prose-invert max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}
        components={{
          img: Img,
          code: Code,
          table: (p) => <table {...p} className="w-full border-collapse border border-border/20 rounded-xl overflow-hidden" />,
          thead: (p) => <thead {...p} className="bg-muted/20" />,
          th: (p) => <th {...p} className="px-3 py-2 border border-border/20 text-left font-semibold text-sm" />,
          td: (p) => <td {...p} className="px-3 py-2 border border-border/20 text-sm" />,
          h1: (p) => <h1 {...p} className="text-xl font-semibold mt-4 mb-2.5 tracking-tight" />,
          h2: (p) => <h2 {...p} className="text-lg font-semibold mt-3.5 mb-2 tracking-tight" />,
          h3: (p) => <h3 {...p} className="text-base font-semibold mt-3 mb-1.5" />,
          ul:  (p) => <ul {...p} className="list-disc pl-5 space-y-1" />,
          ol:  (p) => <ol {...p} className="list-decimal pl-5 space-y-1" />,
          a:   (p) => <a {...p} className="underline underline-offset-4 transition-colors" style={{ color: '#00f0ff' }} target="_blank" />,
        }}
      >
        {sanitizedContent}
      </ReactMarkdown>

      {references?.length > 0 && (
        <div className="mt-4 pt-3 border-t border-border/20">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="w-3.5 h-3.5" style={{ color: '#00f0ff' }} />
            <span className="text-xs font-semibold">相关文档片段</span>
            <span className="text-xs text-muted-foreground/60">({references.length})</span>
          </div>
          <div className="space-y-1.5">
            {references
              .filter((r) => !!r.citationId)
              .map((r, i) => (
                <ReferenceCard key={r.citationId!} citationId={r.citationId!} index={i} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
