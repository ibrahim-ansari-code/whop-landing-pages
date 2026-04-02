"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { buildSpecFromForm, validateQuestionsForm, type CtaType, type CtaEntry } from "@/lib/design-spec";
import { STORAGE_KEYS } from "@/lib/config";
import { InspirationPanel } from "@/components/InspirationPanel";
import { COPY } from "@/lib/copy";

/** Min time between successful "Generate landing pages" navigations (ms). */
const GENERATE_SUBMIT_COOLDOWN_MS = 8000;

const CTA_VALUES: CtaType[] = ["button", "call", "trial", "contact_form", "contact_mailto"];

const defaultCtaEntry: CtaEntry = { type: "button", label: "Get started", url: "" };

const SOCIAL_KEYS = ["twitter", "linkedin", "instagram", "youtube", "github"] as const;

export default function Home() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [companyName, setCompanyName] = useState("");
  const [businessInfo, setBusinessInfo] = useState("");
  const [skillsOrNiches, setSkillsOrNiches] = useState("");
  const [ctaEntries, setCtaEntries] = useState<CtaEntry[]>([{ ...defaultCtaEntry }]);
  const [socials, setSocials] = useState<Record<string, string>>({});
  const [privacyUrl, setPrivacyUrl] = useState("");
  const [termsUrl, setTermsUrl] = useState("");
  const [securityUrl, setSecurityUrl] = useState("");
  const [logoDataUrl, setLogoDataUrl] = useState<string | null>(null);
  const [logoFileName, setLogoFileName] = useState<string | null>(null);
  const [inspirationData, setInspirationData] = useState<Record<string, unknown> | null>(null);
  const [inspirationGate, setInspirationGate] = useState({ submitBlocked: false, scanning: false });
  const [validationError, setValidationError] = useState<string | null>(null);
  const lastGenerateNavAt = useRef(0);
  const generateSubmitLock = useRef(false);

  const onInspirationGateChange = useCallback((gate: { submitBlocked: boolean; scanning: boolean }) => {
    setInspirationGate(gate);
  }, []);

  function handleLogoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 1024 * 1024) {
      setValidationError("Logo image must be under 1 MB");
      return;
    }
    if (!file.type.startsWith("image/")) {
      setValidationError("Please upload an image file (PNG, JPG, SVG, WebP)");
      return;
    }
    setValidationError(null);
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      setLogoDataUrl(result);
      setLogoFileName(file.name);
    };
    reader.readAsDataURL(file);
  }

  function handleContinue(e: React.FormEvent) {
    e.preventDefault();
    setValidationError(null);
    const name = companyName.trim();
    if (name.length < 1) {
      setValidationError("Company name is required");
      return;
    }
    if (name.length > 200) {
      setValidationError("Company name must be at most 200 characters");
      return;
    }
    setStep(2);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setValidationError(null);
    if (generateSubmitLock.current) return;
    if (inspirationGate.submitBlocked) {
      setValidationError(COPY.HOME.WAIT_INSPIRATION);
      return;
    }
    const now = Date.now();
    if (now - lastGenerateNavAt.current < GENERATE_SUBMIT_COOLDOWN_MS) {
      const waitSec = Math.ceil((GENERATE_SUBMIT_COOLDOWN_MS - (now - lastGenerateNavAt.current)) / 1000);
      setValidationError(COPY.HOME.SUBMIT_COOLDOWN(waitSec));
      return;
    }
    const data = {
      companyName: companyName.trim(),
      businessInfo: businessInfo.trim(),
      skillsOrNiches: skillsOrNiches.trim(),
      ctaType: ctaEntries[0]?.type ?? "button",
      ctaEntries: ctaEntries.map((e) => ({
        type: e.type,
        label: e.label.trim() || (e.type === "call" ? "Book a call" : e.type === "trial" ? "Start trial" : e.type === "contact_form" || e.type === "contact_mailto" ? "Contact us" : "Get started"),
        url: e.type === "contact_form" || e.type === "contact_mailto" ? "mailto:" + (e.contactEmail ?? "").trim() : e.url.trim(),
        embedCalendly: e.embedCalendly ?? false,
        contactEmail: e.type === "contact_form" || e.type === "contact_mailto" ? (e.contactEmail ?? "").trim() : undefined,
      })),
      socials: Object.fromEntries(Object.entries(socials).filter(([, v]) => v?.trim())),
      privacyUrl: privacyUrl.trim() || undefined,
      termsUrl: termsUrl.trim() || undefined,
      securityUrl: securityUrl.trim() || undefined,
      logoDataUrl: logoDataUrl || undefined,
    };
    const err = validateQuestionsForm(data);
    if (err) {
      setValidationError(err.message);
      return;
    }
    const spec = buildSpecFromForm(data);
    if (typeof window !== "undefined") {
      sessionStorage.setItem(STORAGE_KEYS.SPEC, JSON.stringify(spec));
      sessionStorage.removeItem("landright-use-critic");
      if (inspirationData) {
        sessionStorage.setItem("landright-competitor-dna", JSON.stringify(inspirationData));
      } else {
        sessionStorage.removeItem("landright-competitor-dna");
      }
    }
    generateSubmitLock.current = true;
    lastGenerateNavAt.current = Date.now();
    router.push("/generate");
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 bg-zinc-900/50 px-4 py-3">
        <div className="mx-auto flex max-w-xl items-center justify-between px-2">
          <h1 className="text-lg font-semibold tracking-tight">{COPY.HOME.TITLE}</h1>
          <Link
            href="/dashboard"
            className="text-sm font-medium text-zinc-400 hover:text-white"
          >
            {COPY.DASHBOARD.HOME_LINK}
          </Link>
        </div>
      </header>
      <div className="mx-auto max-w-xl px-6 py-16">
        <h2 className="text-2xl font-semibold tracking-tight">{COPY.HOME.TITLE}</h2>
        <p className="mt-1 text-sm text-zinc-400">{COPY.HOME.SUBTITLE}</p>
        {validationError && (
          <p className="mt-4 rounded-lg border border-red-800 bg-red-950/50 px-4 py-2 text-sm text-red-200" role="alert">
            {validationError}
          </p>
        )}

        {step === 1 ? (
          <form onSubmit={handleContinue} className="mt-10 space-y-8">
            <div>
              <label htmlFor="companyName" className="block text-sm font-medium text-zinc-300">
                {COPY.HOME.LABELS.COMPANY_NAME}
              </label>
              <input
                id="companyName"
                type="text"
                required
                maxLength={200}
                placeholder={COPY.HOME.PLACEHOLDERS.COMPANY_NAME}
                className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-300">
                Logo (optional)
              </label>
              <p className="mt-1 text-xs text-zinc-500">Upload your company logo. It will appear in the nav bar of generated pages.</p>
              <div className="mt-2 flex items-center gap-3">
                <label className="cursor-pointer rounded-lg border border-dashed border-zinc-600 px-4 py-3 text-sm text-zinc-400 hover:border-zinc-400 hover:text-zinc-300 transition">
                  {logoFileName ? "Change image" : "Upload image"}
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/svg+xml,image/webp"
                    className="hidden"
                    onChange={handleLogoUpload}
                  />
                </label>
                {logoDataUrl && (
                  <div className="flex items-center gap-2">
                    <Image
                      src={logoDataUrl}
                      alt="Logo preview"
                      width={120}
                      height={40}
                      unoptimized
                      className="h-10 w-auto max-w-[120px] rounded border border-zinc-700 bg-white object-contain p-1"
                    />
                    <span className="text-xs text-zinc-500 truncate max-w-[120px]">{logoFileName}</span>
                    <button
                      type="button"
                      onClick={() => { setLogoDataUrl(null); setLogoFileName(null); }}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Remove
                    </button>
                  </div>
                )}
              </div>
            </div>
            <button
              type="submit"
              className="w-full rounded-lg bg-zinc-100 py-3 text-sm font-medium text-zinc-900 transition hover:bg-white"
            >
              {COPY.HOME.CONTINUE}
            </button>
          </form>
        ) : (
          <form onSubmit={handleSubmit} className="mt-10 space-y-8">
            <div className="flex items-center gap-3 text-sm text-zinc-400">
              {logoDataUrl && (
                <Image src={logoDataUrl} alt="Logo" width={100} height={32} unoptimized className="h-8 w-auto max-w-[100px] rounded bg-white object-contain p-0.5" />
              )}
              <span>
                <span className="font-medium text-zinc-300">{COPY.HOME.LABELS.COMPANY_NAME}:</span> {companyName}
              </span>
            </div>
            <div>
              <label htmlFor="business" className="block text-sm font-medium text-zinc-300">
                {COPY.HOME.LABELS.BUSINESS}
              </label>
              <textarea
                id="business"
                required
                rows={4}
                maxLength={2000}
                placeholder={COPY.HOME.PLACEHOLDERS.BUSINESS}
                className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
                value={businessInfo}
                onChange={(e) => setBusinessInfo(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="skills" className="block text-sm font-medium text-zinc-300">
                {COPY.HOME.LABELS.SKILLS}
              </label>
              <input
                id="skills"
                type="text"
                maxLength={500}
                placeholder={COPY.HOME.PLACEHOLDERS.SKILLS}
                className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
                value={skillsOrNiches}
                onChange={(e) => setSkillsOrNiches(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-300">
                {COPY.HOME.LABELS.CTA}
              </label>
              <div className="mt-3 space-y-4">
                {ctaEntries.map((entry, index) => (
                  <div
                    key={index}
                    className="rounded-lg border border-zinc-700 bg-zinc-900 p-4 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-zinc-500">CTA {index + 1}</span>
                      {ctaEntries.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setCtaEntries((prev) => prev.filter((_, i) => i !== index))}
                          className="text-xs text-red-400 hover:text-red-300"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">{COPY.HOME.CTA_TYPE}</label>
                      <select
                        value={entry.type ?? "button"}
                        onChange={(ev) =>
                          setCtaEntries((prev) =>
                            prev.map((item, i) => (i === index ? { ...item, type: ev.target.value as CtaType } : item))
                          )
                        }
                        className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                      >
                        {CTA_VALUES.map((v) => (
                          <option key={v} value={v}>
                            {COPY.HOME.CTA_OPTIONS[v]}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">{COPY.HOME.CTA_LABEL}</label>
                      <input
                        type="text"
                        value={entry.label ?? ""}
                        onChange={(ev) =>
                          setCtaEntries((prev) =>
                            prev.map((item, i) => (i === index ? { ...item, label: ev.target.value } : item))
                          )
                        }
                        placeholder={entry.type === "call" ? "Book a call" : entry.type === "trial" ? "Start trial" : entry.type === "contact_form" || entry.type === "contact_mailto" ? "Contact us" : "Get started"}
                        className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500"
                      />
                    </div>
                    {/* URL field: show for button, call, trial — hide for contact (we ask for email instead) */}
                    {(entry.type !== "contact_form" && entry.type !== "contact_mailto") && (
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">{COPY.HOME.CTA_URL}</label>
                        <input
                          type="url"
                          value={entry.url ?? ""}
                          onChange={(ev) =>
                            setCtaEntries((prev) =>
                              prev.map((item, i) => (i === index ? { ...item, url: ev.target.value } : item))
                            )
                          }
                          placeholder={entry.type === "call" ? "https://calendly.com/you/30min" : "https://..."}
                          className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500"
                        />
                      </div>
                    )}
                    {/* Email field: only for Contact us (form or mailto) — the page owner's email */}
                    {(entry.type === "contact_form" || entry.type === "contact_mailto") && (
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">{COPY.HOME.CTA_CONTACT_EMAIL}</label>
                        <input
                          type="email"
                          value={entry.contactEmail ?? ""}
                          onChange={(ev) =>
                            setCtaEntries((prev) =>
                              prev.map((item, i) => (i === index ? { ...item, contactEmail: ev.target.value } : item))
                            )
                          }
                          placeholder="you@company.com"
                          className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500"
                        />
                      </div>
                    )}
                    {entry.type === "call" && (
                      <label className="flex items-center gap-2 text-sm text-zinc-400">
                        <input
                          type="checkbox"
                          checked={entry.embedCalendly ?? false}
                          onChange={(ev) =>
                            setCtaEntries((prev) =>
                              prev.map((item, i) => (i === index ? { ...item, embedCalendly: ev.target.checked } : item))
                            )
                          }
                          className="h-4 w-4 rounded border-zinc-600 bg-zinc-800"
                        />
                        {COPY.HOME.CTA_EMBED_CALENDLY}
                      </label>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setCtaEntries((prev) => [...prev, { ...defaultCtaEntry }])}
                  className="text-sm text-zinc-400 hover:text-zinc-300 border border-dashed border-zinc-600 rounded-lg w-full py-2"
                >
                  {COPY.HOME.CTA_ADD}
                </button>
              </div>
            </div>
            <InspirationPanel
              onInspirationChange={setInspirationData}
              onInspirationGateChange={onInspirationGateChange}
            />
            <div className="mt-8">
              <h3 className="text-sm font-medium text-zinc-300">{COPY.HOME.SOCIALS}</h3>
              <div className="mt-2 space-y-2">
                {SOCIAL_KEYS.map((key) => (
                  <div key={key}>
                    <label className="block text-xs text-zinc-500 mb-0.5">
                      {key === "twitter" && COPY.HOME.SOCIAL_TWITTER}
                      {key === "linkedin" && COPY.HOME.SOCIAL_LINKEDIN}
                      {key === "instagram" && COPY.HOME.SOCIAL_INSTAGRAM}
                      {key === "youtube" && COPY.HOME.SOCIAL_YOUTUBE}
                      {key === "github" && COPY.HOME.SOCIAL_GITHUB}
                    </label>
                    <input
                      type="url"
                      value={socials[key] ?? ""}
                      onChange={(e) => setSocials((prev) => ({ ...prev, [key]: e.target.value }))}
                      placeholder="https://..."
                      className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500"
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-6">
              <h3 className="text-sm font-medium text-zinc-300">{COPY.HOME.LEGAL}</h3>
              <div className="mt-2 space-y-2">
                <div>
                  <label className="block text-xs text-zinc-500 mb-0.5">{COPY.HOME.PRIVACY_URL}</label>
                  <input
                    type="url"
                    value={privacyUrl ?? ""}
                    onChange={(e) => setPrivacyUrl(e.target.value)}
                    placeholder="https://..."
                    className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-0.5">{COPY.HOME.TERMS_URL}</label>
                  <input
                    type="url"
                    value={termsUrl ?? ""}
                    onChange={(e) => setTermsUrl(e.target.value)}
                    placeholder="https://..."
                    className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-0.5">{COPY.HOME.SECURITY_URL}</label>
                  <input
                    type="url"
                    value={securityUrl ?? ""}
                    onChange={(e) => setSecurityUrl(e.target.value)}
                    placeholder="https://..."
                    className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500"
                  />
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-4">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="rounded-lg border border-zinc-600 px-4 py-3 text-sm font-medium text-zinc-300 transition hover:bg-zinc-800"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={inspirationGate.submitBlocked}
                className="flex-1 rounded-lg bg-zinc-100 py-3 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {inspirationGate.scanning ? COPY.HOME.INSPIRATION_SCANNING : COPY.HOME.SUBMIT}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
