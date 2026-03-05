import { LIMITS } from "@/lib/config";

export type CtaType = "button" | "call" | "trial" | "contact_form" | "contact_mailto";

export interface CtaEntry {
  type: CtaType;
  label: string;
  url: string;
  embedCalendly?: boolean;
  /** Email for contact_form and contact_mailto (required when type is either). */
  contactEmail?: string;
}

export type ColorSchemePreset = "neutral" | "warm" | "cool" | "dark" | "light" | "brand";

export interface ColorScheme {
  preset?: ColorSchemePreset;
  primary?: string;
  secondary?: string;
  background?: string;
  text?: string;
}

export type ThemeVibe = "minimal" | "editorial" | "bold";

export interface FontPreference {
  preferred?: string;
  custom?: string;
}

export interface WebsiteInformation {
  name: string;
  tagline: string;
  whatTheyDo: string;
  valueProp?: string;
}

/** Optional social links (platform key -> URL). */
export type Socials = Partial<Record<string, string>>;

export interface DesignSpec {
  websiteInformation: WebsiteInformation;
  skillsOrNiches: string[];
  goals: string[];
  ctaType: CtaType;
  ctaEntries?: CtaEntry[];
  priorities?: string[];
  features?: string[];
  style?: string;
  colorScheme?: ColorScheme;
  theme?: ThemeVibe;
  fonts?: FontPreference;
  referenceSites?: string[];
  /** Optional social links (e.g. twitter, linkedin, instagram, youtube, github). */
  socials?: Socials;
  privacyUrl?: string;
  termsUrl?: string;
  securityUrl?: string;
  /** Base64 data URL for a logo image uploaded by the user. */
  logoDataUrl?: string;
}

export interface QuestionsFormData {
  companyName: string;
  businessInfo: string;
  skillsOrNiches: string;
  ctaType: CtaType;
  ctaEntries?: CtaEntry[];
  colorPreset?: string;
  colorPrimary?: string;
  colorSecondary?: string;
  colorBackground?: string;
  colorText?: string;
  theme?: ThemeVibe;
  referenceSites?: string;
  socials?: Socials;
  privacyUrl?: string;
  termsUrl?: string;
  securityUrl?: string;
  /** Base64 data URL for a logo image uploaded by the user. */
  logoDataUrl?: string;
}

export interface ValidationError {
  field: keyof QuestionsFormData;
  message: string;
}

/** Client-side validation for the questions form. Returns first error or null. */
export function validateQuestionsForm(data: QuestionsFormData): ValidationError | null {
  const company = (data.companyName || "").trim();
  if (company.length < 1) {
    return { field: "companyName", message: "Company name is required" };
  }
  if (company.length > 200) {
    return { field: "companyName", message: "Company name must be at most 200 characters" };
  }
  const business = data.businessInfo.trim();
  if (business.length < LIMITS.BUSINESS_INFO_MIN_LENGTH) {
    return { field: "businessInfo", message: `Business info must be at least ${LIMITS.BUSINESS_INFO_MIN_LENGTH} characters` };
  }
  if (business.length > LIMITS.BUSINESS_INFO_MAX_LENGTH) {
    return { field: "businessInfo", message: `Business info must be at most ${LIMITS.BUSINESS_INFO_MAX_LENGTH} characters` };
  }
  if (data.skillsOrNiches.length > LIMITS.SKILLS_MAX_LENGTH) {
    return { field: "skillsOrNiches", message: `Skills/niches must be at most ${LIMITS.SKILLS_MAX_LENGTH} characters` };
  }
  const validCta: CtaType[] = ["button", "call", "trial", "contact_form", "contact_mailto"];
  if (!validCta.includes(data.ctaType)) {
    return { field: "ctaType", message: "Invalid CTA type" };
  }
  const entries = data.ctaEntries ?? [];
  if (entries.length === 0) {
    return { field: "ctaType", message: "Add at least one CTA" };
  }
  const urlLike = /^https?:\/\/[^\s]+$/;
  const emailLike = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    if (!validCta.includes(e.type)) {
      return { field: "ctaType", message: `CTA ${i + 1}: Invalid type` };
    }
    if (e.type === "contact_form" || e.type === "contact_mailto") {
      const email = (e.contactEmail ?? "").trim();
      if (!email) {
        return { field: "ctaType", message: `CTA ${i + 1}: Email is required` };
      }
      if (!emailLike.test(email)) {
        return { field: "ctaType", message: `CTA ${i + 1}: Enter a valid email address` };
      }
    } else {
      if (!e.url?.trim()) {
        return { field: "ctaType", message: `CTA ${i + 1}: Link URL is required` };
      }
      if (!urlLike.test(e.url.trim())) {
        return { field: "ctaType", message: `CTA ${i + 1}: Enter a valid URL (e.g. https://calendly.com/you/30min)` };
      }
    }
  }
  const optUrlLike = /^https?:\/\/[^\s]+$/;
  if (data.privacyUrl?.trim() && !optUrlLike.test(data.privacyUrl.trim())) {
    return { field: "privacyUrl", message: "Privacy URL must be a valid http(s) URL" };
  }
  if (data.termsUrl?.trim() && !optUrlLike.test(data.termsUrl.trim())) {
    return { field: "termsUrl", message: "Terms URL must be a valid http(s) URL" };
  }
  if (data.securityUrl?.trim() && !optUrlLike.test(data.securityUrl.trim())) {
    return { field: "securityUrl", message: "Security URL must be a valid http(s) URL" };
  }
  const socials = data.socials ?? {};
  for (const [key, val] of Object.entries(socials)) {
    if (val && typeof val === "string" && val.trim() && !optUrlLike.test(val.trim())) {
      return { field: "socials", message: `Social link ${key} must be a valid URL` };
    }
  }
  const validThemes: ThemeVibe[] = ["minimal", "editorial", "bold"];
  if (data.theme != null && typeof data.theme === "string" && !validThemes.includes(data.theme as ThemeVibe)) {
    return { field: "theme", message: "Invalid theme" };
  }
  if (data.referenceSites != null && data.referenceSites.length > LIMITS.REFERENCE_SITES_MAX_LENGTH) {
    return { field: "referenceSites", message: `Reference sites must be at most ${LIMITS.REFERENCE_SITES_MAX_LENGTH} characters` };
  }
  const hexLike = /^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/;
  if (data.colorPrimary?.trim() && !hexLike.test(data.colorPrimary.trim()) && !/^[a-zA-Z]+$/.test(data.colorPrimary.trim())) {
    return { field: "colorPrimary", message: "Use a hex color (e.g. #1a1a1a) or a color name" };
  }
  if (data.colorSecondary?.trim() && !hexLike.test(data.colorSecondary.trim()) && !/^[a-zA-Z]+$/.test(data.colorSecondary.trim())) {
    return { field: "colorSecondary", message: "Use a hex color or a color name" };
  }
  return null;
}

const VALID_COLOR_PRESETS: ColorSchemePreset[] = ["neutral", "warm", "cool", "dark", "light", "brand"];

/** Build design spec from form data (no API). */
export function buildSpecFromForm(data: QuestionsFormData): DesignSpec {
  const skills = data.skillsOrNiches
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const name = (data.companyName || "").trim();
  const spec: DesignSpec = {
    websiteInformation: {
      name: name || "",
      tagline: "",
      whatTheyDo: data.businessInfo.trim(),
    },
    skillsOrNiches: skills,
    goals: [],
    ctaType: data.ctaType,
    ctaEntries: data.ctaEntries?.length ? data.ctaEntries : undefined,
    priorities: [],
    features: skills.length ? skills : undefined,
  };

  if (!spec.websiteInformation.name && data.businessInfo.trim()) {
    const firstLine = data.businessInfo.trim().split("\n")[0] || "";
    const parts = firstLine.split(/[–—:]/).map((s) => s.trim());
    if (parts[0]) spec.websiteInformation.name = parts[0];
    if (parts[1]) spec.websiteInformation.tagline = parts[1];
  }
  spec.websiteInformation.whatTheyDo = data.businessInfo.trim();

  if (data.colorPreset && VALID_COLOR_PRESETS.includes(data.colorPreset as ColorSchemePreset)) {
    spec.colorScheme = { preset: data.colorPreset as ColorSchemePreset };
    if (data.colorPrimary?.trim()) spec.colorScheme.primary = data.colorPrimary.trim();
    if (data.colorSecondary?.trim()) spec.colorScheme.secondary = data.colorSecondary.trim();
    if (data.colorBackground?.trim()) spec.colorScheme.background = data.colorBackground.trim();
    if (data.colorText?.trim()) spec.colorScheme.text = data.colorText.trim();
  }

  if (data.theme) spec.theme = data.theme;

  if (data.referenceSites?.trim()) {
    spec.referenceSites = data.referenceSites
      .trim()
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 20);
  }

  if (data.socials && typeof data.socials === "object") {
    const cleaned: Socials = {};
    for (const [k, v] of Object.entries(data.socials)) {
      if (v && typeof v === "string" && v.trim()) cleaned[k] = v.trim();
    }
    if (Object.keys(cleaned).length) spec.socials = cleaned;
  }
  if (data.privacyUrl?.trim()) spec.privacyUrl = data.privacyUrl.trim();
  if (data.termsUrl?.trim()) spec.termsUrl = data.termsUrl.trim();
  if (data.securityUrl?.trim()) spec.securityUrl = data.securityUrl.trim();
  if (data.logoDataUrl) spec.logoDataUrl = data.logoDataUrl;

  return spec;
}
