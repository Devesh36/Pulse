import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (path[0] !== "v1")
    return Response.json({ detail: "Unknown API path" }, { status: 404 });
  const base = process.env.PULSE_API_URL || "http://127.0.0.1:8000";
  // Encode each segment: no URL or host can be supplied by a browser request.
  const target = `${base}/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  for (const name of [
    "content-type",
    "cookie",
    "origin",
    "last-event-id",
    "authorization",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method)
        ? undefined
        : await request.text(),
      cache: "no-store",
      signal: request.signal,
      redirect: "error",
    });
    const output = new Headers();
    for (const name of [
      "content-type",
      "set-cookie",
      "cache-control",
      "x-accel-buffering",
      "retry-after",
    ]) {
      const value = upstream.headers.get(name);
      if (value) output.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return Response.json(
      { detail: "Pulse API is unreachable. Check the backend and database." },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
