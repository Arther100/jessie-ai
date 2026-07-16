"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";

interface Props {
  content: string;
}

export function ReportMarkdown({ content }: Props) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          table: ({ children }) => (
            <div className="overflow-x-auto my-4">
              <table className="min-w-full border-collapse border border-gray-300 dark:border-gray-600 text-sm">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-gray-300 dark:border-gray-600 px-3 py-2 bg-gray-100 dark:bg-gray-800 font-semibold text-left">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-300 dark:border-gray-600 px-3 py-2">
              {children}
            </td>
          ),
          code: ({ className, children, ...props }) => {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return (
                <code className={`${className} rounded text-sm`} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className="bg-gray-100 dark:bg-gray-800 rounded px-1 py-0.5 text-sm font-mono" {...props}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="rounded-lg bg-gray-900 p-4 overflow-x-auto text-sm">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-indigo-400 bg-indigo-50 dark:bg-indigo-950 pl-4 py-2 rounded-r-lg my-3 italic text-gray-700 dark:text-gray-300">
              {children}
            </blockquote>
          ),
          input: ({ type, checked }) => {
            if (type === "checkbox") {
              return (
                <input
                  type="checkbox"
                  defaultChecked={checked}
                  className="mr-1 rounded cursor-pointer"
                />
              );
            }
            return <input type={type} />;
          },
          h1: ({ children }) => (
            <h1 className="text-2xl font-bold mt-6 mb-3 text-gray-900 dark:text-gray-100 border-b pb-2">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xl font-bold mt-5 mb-2 text-gray-800 dark:text-gray-200">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-lg font-semibold mt-4 mb-2 text-gray-700 dark:text-gray-300">
              {children}
            </h3>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
