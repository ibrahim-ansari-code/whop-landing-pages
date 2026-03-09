import unittest

import main


SAMPLE_TSX = """
"use client";

export default function Variant() {
  return (
    <main>
      <section data-landright-section="hero" className="px-6 py-16">
        <h1>Grow faster</h1>
        <a href="/demo" className="hero-cta inline-flex rounded-xl bg-black px-6 py-3 text-white">Book Demo</a>
      </section>
      <section data-landright-section="pricing" className="px-6 py-16">
        <button className="pricing-cta rounded-xl border px-5 py-3">Start Trial</button>
      </section>
    </main>
  );
}
""".strip()


class CtaAlignTests(unittest.TestCase):
    def test_count_changed_lines_handles_insert_without_counting_rest_of_file(self):
        old = "a\nb\nc\nd"
        new = "a\nx\nb\nc\nd"
        self.assertEqual(main._count_changed_lines(old, new), 1)

    def test_apply_cta_ops_accepts_section_alias_and_source_less_add(self):
        result = main._apply_cta_ops(
            SAMPLE_TSX,
            [{
                "op": "add_cta",
                "section": "hero",
                "new_html": '<button onClick={() => setCalendlyOpen(true)} className="inline-flex items-center rounded-xl bg-orange-500 px-6 py-3 text-white">Get Pricing</button>',
            }],
        )
        self.assertTrue(result)
        self.assertIn('data-landright-section="hero"', result)
        self.assertIn('Get Pricing</button>', result)
        self.assertIn('bg-orange-500', result)
        self.assertNotIn("setCalendlyOpen", result)
        self.assertIn('type="button"', result)

    def test_extract_alignment_tsx_accepts_json_payload(self):
        payload = '{"tsx":"```tsx\\n\\"use client\\";\\nexport default function Variant(){return <div data-landright-section=\\"hero\\">Hi</div>}\\n```"}'
        result = main._extract_alignment_tsx(payload)
        self.assertIn('"use client"', result)
        self.assertIn('data-landright-section="hero"', result)


if __name__ == "__main__":
    unittest.main()
