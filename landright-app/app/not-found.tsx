import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center px-6">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-zinc-400">The page you’re looking for doesn’t exist or couldn’t be loaded.</p>
      <div className="mt-8 flex gap-4">
        <Link
          href="/"
          className="rounded-lg bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
        >
          Home
        </Link>
        <Link
          href="/generate"
          className="rounded-lg border border-zinc-600 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800"
        >
          Generate landing page
        </Link>
      </div>
    </div>
  );
}
