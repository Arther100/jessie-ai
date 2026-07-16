import { NextRequest, NextResponse } from "next/server";

const BASE = process.env.NEXT_PUBLIC_JESSIE_API ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const id = searchParams.get("id");
  const path = searchParams.get("path");

  try {
    if (id) {
      const res = await fetch(`${BASE}/reports/${id}`, { cache: "no-store" });
      if (!res.ok) {
        return NextResponse.json({ error: `Report ${id} not found` }, { status: res.status });
      }
      const data = await res.json() as { markdown_content?: string };
      const md = data.markdown_content ?? "";
      return new NextResponse(md, {
        headers: {
          "Content-Type": "text/markdown; charset=utf-8",
          "Content-Disposition": `attachment; filename="jessie-report-${id}.md"`,
        },
      });
    }

    if (path) {
      const res = await fetch(
        `${BASE}/reports/file?path=${encodeURIComponent(path)}`,
        { cache: "no-store" },
      );
      if (!res.ok) {
        return NextResponse.json(
          { error: "Report file not found on backend. Re-run review or use Download from results." },
          { status: res.status },
        );
      }
      const md = await res.text();
      return new NextResponse(md, {
        headers: {
          "Content-Type": "text/markdown; charset=utf-8",
          "Content-Disposition": 'attachment; filename="jessie-report.md"',
        },
      });
    }

    return NextResponse.json({ error: "Provide id or path" }, { status: 400 });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Proxy failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
