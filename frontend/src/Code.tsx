import { Highlight, themes } from "prism-react-renderer";

/** Highlighted code, rendered as React elements rather than an HTML string. */
export function Code({ code, language }: { code: string; language: "sql" | "json" }) {
  return (
    <Highlight code={code} language={language} theme={themes.github}>
      {({ style, tokens, getLineProps, getTokenProps }) => (
        <pre style={style}>
          {tokens.map((line, i) => (
            <div key={i} {...getLineProps({ line })}>
              {line.map((token, j) => (
                <span key={j} {...getTokenProps({ token })} />
              ))}
            </div>
          ))}
        </pre>
      )}
    </Highlight>
  );
}
