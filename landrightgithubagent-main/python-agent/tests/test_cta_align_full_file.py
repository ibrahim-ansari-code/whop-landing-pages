import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main


SAMPLE_TSX = """
"use client";

import Script from "next/script";

export default function Variant() {
  return (
    <main>
      <section data-landright-section="hero" className="px-6 py-16">
        <h1>Grow faster</h1>
        <a href="/demo" className="hero-cta inline-flex rounded-xl bg-black px-6 py-3 text-white">Book Demo</a>
      </section>
      <section data-landright-section="pricing" className="px-6 py-16">
        <div className="calendly-inline-widget" data-url="https://calendly.com/demo"></div>
        <button className="pricing-cta rounded-xl border px-5 py-3">Start Trial</button>
      </section>
      <Script src="https://assets.calendly.com/assets/external/widget.js" strategy="afterInteractive" />
    </main>
  );
}
""".strip()


class _FakeAnthropicClient:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.messages = self

    def create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(text=self._response_text)])


class CtaAlignFullFileTests(unittest.TestCase):
    def test_validate_alignment_candidate_rejects_missing_frozen_embed(self):
        candidate = SAMPLE_TSX.replace('        <div className="calendly-inline-widget" data-url="https://calendly.com/demo"></div>\n', "")
        candidate = candidate.replace('      <Script src="https://assets.calendly.com/assets/external/widget.js" strategy="afterInteractive" />\n', "")
        ok, reason = main._validate_alignment_candidate(SAMPLE_TSX, candidate)
        self.assertFalse(ok)
        self.assertIn("calendly", reason)

    def test_call_claude_align_cta_accepts_full_tsx_response(self):
        llm_response = """```tsx
"use client";

import Script from "next/script";

export default function Variant() {
  return (
    <main>
      <section data-landright-section="hero" className="px-6 py-16">
        <div className="inline-flex items-center gap-3">
          <a href="/demo" className="hero-cta inline-flex rounded-xl bg-black px-6 py-3 text-white">Book Demo</a>
          <button type="button" className="inline-flex rounded-xl border border-orange-500 px-6 py-3 text-orange-500">Claim Your Spot</button>
        </div>
        <h1>Grow faster</h1>
      </section>
      <section data-landright-section="pricing" className="px-6 py-16">
        <div className="calendly-inline-widget" data-url="https://calendly.com/demo"></div>
        <button className="pricing-cta rounded-xl border px-5 py-3">Start Trial</button>
      </section>
      <Script src="https://assets.calendly.com/assets/external/widget.js" strategy="afterInteractive" />
    </main>
  );
}
```"""
        fake_client = _FakeAnthropicClient(llm_response)
        with patch.object(main, "ANTHROPIC_API_KEY", "test-key"):
            with patch("anthropic.Anthropic", return_value=fake_client):
                result = main._call_claude_align_cta(
                    design_skill="You are a frontend designer.",
                    best_cta_description="Hero has two prominent CTAs and pricing keeps a secondary CTA.",
                    underperforming_tsx=SAMPLE_TSX,
                    best_variant_id="variant-1",
                    best_clicks=10,
                    underperforming_clicks=2,
                    best_section_times={"hero": 120.0},
                    underperforming_section_times={"hero": 90.0, "pricing": 15.0},
                )
        self.assertTrue(result)
        self.assertIn("Claim Your Spot", result)
        self.assertIn("calendly-inline-widget", result)
        self.assertIn("widget.js", result)
        self.assertIn('data-landright-section="hero"', result)
        self.assertNotEqual(result, SAMPLE_TSX)

    def test_call_claude_align_cta_section_rewrite_updates_selected_section(self):
        llm_response = """<!-- LANDRIGHT-SECTION:hero -->
<section data-landright-section="hero" className="px-6 py-16">
  <div className="inline-flex items-center gap-3">
    <a href="/demo" className="hero-cta inline-flex rounded-xl bg-black px-6 py-3 text-white">Book Demo</a>
    <button type="button" className="inline-flex rounded-xl border border-orange-500 px-6 py-3 text-orange-500">Claim Your Spot</button>
  </div>
  <h1>Grow faster</h1>
</section>
<!-- /LANDRIGHT-SECTION -->"""
        fake_client = _FakeAnthropicClient(llm_response)
        with patch("anthropic.Anthropic", return_value=fake_client):
            result = main._call_claude_align_cta_section_rewrite(
                design_skill="You are a frontend designer.",
                best_cta_description="Hero has two prominent CTAs.",
                underperforming_tsx=SAMPLE_TSX,
                best_variant_id="variant-1",
                underperforming_variant_id="variant-2",
            )
        self.assertTrue(result)
        self.assertIn("Claim Your Spot", result)
        self.assertIn("calendly-inline-widget", result)
        self.assertIn('data-landright-section="pricing"', result)

    def test_call_claude_align_cta_rejects_non_tsx_json_plan(self):
        llm_response = """```json
{"operations":[{"op":"add_cta","target_section":"hero","new_html":"<button>Buy</button>"}]}
```"""
        fake_client = _FakeAnthropicClient(llm_response)
        with patch.object(main, "ANTHROPIC_API_KEY", "test-key"):
            with patch("anthropic.Anthropic", return_value=fake_client):
                result = main._call_claude_align_cta(
                    design_skill="You are a frontend designer.",
                    best_cta_description="Hero has two prominent CTAs.",
                    underperforming_tsx=SAMPLE_TSX,
                    best_variant_id="variant-1",
                )
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
