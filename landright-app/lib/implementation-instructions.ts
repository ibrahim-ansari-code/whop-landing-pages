/** Implementation instructions for TSX export (Next.js). */
export const IMPLEMENTATION_INSTRUCTIONS_TSX = [
  "Add the file as app/page.tsx or app/(marketing)/page.tsx in your Next.js project.",
  "Ensure Tailwind and next/font are configured (they are in a default Next.js app).",
  "Run npm run dev to preview. Run npm run build to check for TypeScript errors.",
  "To customize: edit the component; look for the Hero, Features, CTA, and Footer sections.",
] as const;

/** Implementation instructions for HTML export (template fallback). */
export const IMPLEMENTATION_INSTRUCTIONS_HTML = [
  "Save the file as index.html and open it in a browser to preview.",
  "Tailwind is included via CDN; for production you can switch to a build step if needed.",
  "To deploy: use Netlify Drop, Vercel, GitHub Pages, or any static host.",
  "To customize: edit the HTML; look for the hero, CTA, and feature sections.",
] as const;
