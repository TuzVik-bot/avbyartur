"use client";

type GlobalErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

const pageStyle = { margin: 0, minHeight: "100vh", display: "grid", placeItems: "center", padding: 24, fontFamily: "Inter, Arial, sans-serif", color: "#222b3e", background: "#f8faff" } as const;
const panelStyle = { maxWidth: 520, padding: 32, border: "1px solid #dfe5ef", borderRadius: 8, background: "#fff" } as const;
const buttonStyle = { minHeight: 44, padding: "9px 14px", border: 0, borderRadius: 6, background: "#3f5cc4", color: "#fff", font: "inherit", fontWeight: 700, cursor: "pointer" } as const;
const linkStyle = { minHeight: 44, display: "inline-flex", alignItems: "center", marginLeft: 12, color: "#2946a5", fontWeight: 700 } as const;

// Replaces the root layout when it fails, so it must render its own document without app providers or styles.
export default function GlobalError({ reset }: GlobalErrorProps) {
  return (
    <html lang="ru">
      <body style={pageStyle}>
        <main style={panelStyle} role="alert">
          <h1 style={{ margin: "0 0 12px", fontSize: 26 }}>Что-то пошло не так</h1>
          <p style={{ margin: "0 0 24px", color: "#69758a", lineHeight: 1.55 }}>Попробуйте повторить загрузку. Если ошибка не исчезнет, вернитесь на главную страницу.</p>
          <button style={buttonStyle} type="button" onClick={() => reset()}>Повторить</button>
          <a style={linkStyle} href="/">На главную</a>
        </main>
      </body>
    </html>
  );
}
