import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import json from "highlight.js/lib/languages/json";
import yaml from "highlight.js/lib/languages/yaml";
import markdown from "highlight.js/lib/languages/markdown";
import css from "highlight.js/lib/languages/css";
import xml from "highlight.js/lib/languages/xml";
import bash from "highlight.js/lib/languages/bash";
import sql from "highlight.js/lib/languages/sql";
import java from "highlight.js/lib/languages/java";
import go from "highlight.js/lib/languages/go";
import rust from "highlight.js/lib/languages/rust";
import { useEffect, useMemo, useRef } from "react";

Object.entries({ python, javascript, typescript, json, yaml, markdown, css, xml, bash, sql, java, go, rust }).forEach(([n, l]) => hljs.registerLanguage(n, l));
const MAP: Record<string, string> = { Python: "python", JavaScript: "javascript", TypeScript: "typescript", JSON: "json", YAML: "yaml", Markdown: "markdown", CSS: "css", HTML: "xml", XML: "xml", Shell: "bash", SQL: "sql", Java: "java", Go: "go", Rust: "rust" };
const LH = 20;

export function CodeViewer({ content, language, highlight }: { content: string; language: string; highlight?: { start: number; end: number } }) {
  const box = useRef<HTMLDivElement>(null);
  const html = useMemo(() => {
    const lang = MAP[language];
    try { return lang ? hljs.highlight(content, { language: lang }).value : hljs.highlightAuto(content.slice(0, 20000)).value; }
    catch { return content.replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
  }, [content, language]);
  const count = content.split("\n").length;

  useEffect(() => {
    if (highlight && box.current) box.current.scrollTo({ top: Math.max(0, (highlight.start - 4) * LH), behavior: "smooth" });
    else box.current?.scrollTo({ top: 0 });
  }, [content, highlight?.start, highlight?.end]);

  return (
    <div ref={box} className="relative h-full overflow-auto bg-ink-950 font-mono text-[13px]" style={{ lineHeight: `${LH}px` }}>
      <div className="relative flex min-w-max">
        {highlight && <div className="pointer-events-none absolute left-0 right-0 border-l-2 border-accent bg-accent/10" style={{ top: 12 + (highlight.start - 1) * LH, height: (highlight.end - highlight.start + 1) * LH }} />}
        <div aria-hidden className="sticky left-0 z-10 select-none bg-ink-950 py-3 pl-3 pr-4 text-right text-slate-600">
          {Array.from({ length: count }, (_, i) => <div key={i}>{i + 1}</div>)}
        </div>
        <pre className="py-3 pr-6"><code className="hljs !bg-transparent !p-0" dangerouslySetInnerHTML={{ __html: html }} /></pre>
      </div>
    </div>
  );
}
