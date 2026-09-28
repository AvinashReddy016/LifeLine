import { useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  // LLM output is untrusted: never follow model-supplied URLs or raw HTML.
  a: ({ children }) => <>{children}</>,
  img: ({ alt }) => (alt ? <em>{alt}</em> : null),
  code: ({ className, children }) => {
    if (className?.includes("language-")) {
      return <code className={`md-code ${className}`}>{children}</code>;
    }
    const text = String(children);
    const isRecordId = /^REC-\d{3,}$/.test(text.trim());
    return <code className={isRecordId ? "md-rid" : "md-inline-code"}>{children}</code>;
  },
  table: ({ children }) => (
    <div className="md-table-scroll">
      <table className="md-table">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="md-thead">{children}</thead>,
  th: ({ children }) => <th className="md-th">{children}</th>,
  td: ({ children }) => <td className="md-td">{children}</td>,
  tr: ({ children }) => <tr className="md-tr">{children}</tr>,
  ul: ({ children }) => <ul className="md-ul">{children}</ul>,
  ol: ({ children }) => <ol className="md-ol">{children}</ol>,
  li: ({ children }) => <li className="md-li">{children}</li>,
  p: ({ children }) => <p className="md-p">{children}</p>,
  strong: ({ children }) => <strong className="md-strong">{children}</strong>,
  h1: ({ children }) => <h4 className="md-h md-h1">{children}</h4>,
  h2: ({ children }) => <h4 className="md-h md-h2">{children}</h4>,
  h3: ({ children }) => <h5 className="md-h md-h3">{children}</h5>,
  h4: ({ children }) => <h6 className="md-h md-h4">{children}</h6>,
  h5: ({ children }) => <h6 className="md-h md-h5">{children}</h6>,
  blockquote: ({ children }) => <blockquote className="md-quote">{children}</blockquote>,
  hr: () => <hr className="md-hr" />,
};

/**
 * Renders LLM markdown as real UI: GFM tables, bold, headings, lists.
 * Bare record ids (REC-xxxx) become inline chips. Raw HTML is never
 * executed; links are neutered since the content is untrusted model output.
 */
export function Markdown({ children }: { children: string }) {
  // Wrap bare record ids in backticks so they render as inline chips.
  // Existing backtick-wrapped ids are left untouched by the negative lookarounds.
  const processed = useMemo(
    () =>
      children
        .replace(/\r\n/g, "\n")
        .replace(/(?<!`)REC-(\d{3,})(?!`)/g, "`REC-$1`"),
    [children],
  );
  const memoComponents = useMemo(() => components, []);

  return (
    <div className="md-root">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={memoComponents} skipHtml>
        {processed}
      </ReactMarkdown>
    </div>
  );
}
