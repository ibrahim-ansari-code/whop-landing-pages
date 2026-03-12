"use client";

import {Bebas_Neue, Manrope} from 'next/font/google';

const bebas = Bebas_Neue({ subsets: ['latin'], weight: '400', variable: '--font-bebas' });
const manrope = Manrope({ subsets: ['latin'], variable: '--font-manrope' });

export default function SimGymV4() {
  return (
    <div className={`${bebas.variable} ${manrope.variable} min-h-screen bg-[#080C10] text-[#F0EDE8] overflow-x-hidden`} style={{ fontFamily: 'var(--font-manrope), sans-serif' }}>
      {/* Film grain SVG filter */}
      <svg style={{ position: 'fixed', top: 0, left: 0, width: 0, height: 0 }}>
        <defs>
          <filter id="grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
            <feBlend in="SourceGraphic" mode="overlay" result="blend" />
            <feComposite in="blend" in2="SourceGraphic" operator="in" />
          </filter>
        </defs>
      </svg>

      {/* Grain overlay */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          pointerEvents: 'none',
          zIndex: 50,
          opacity: 0.035,
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'repeat',
          backgroundSize: '128px 128px',
        }}
      />

      {/* NAV */}
      <nav data-landright-section="Nav" className="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-6 md:px-12 py-5" style={{ background: 'linear-gradient(to bottom, rgba(8,12,16,0.95) 0%, rgba(8,12,16,0) 100%)' }}>
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-sm flex items-center justify-center" style={{ background: '#E8323C' }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="7" width="3" height="6" fill="white" />
              <rect x="5.5" y="4" width="3" height="9" fill="white" />
              <rect x="10" y="1" width="3" height="12" fill="white" />
            </svg>
          </div>
          <span style={{ fontFamily: 'var(--font-bebas), sans-serif', fontSize: '1.4rem', letterSpacing: '0.08em', color: '#F0EDE8' }}>SimGym</span>
        </div>
        <a
          href="https://example.com/signup"
          className="hidden md:inline-flex items-center gap-2 px-5 py-2 text-sm font-semibold tracking-wide transition-all duration-200 hover:opacity-90"
          style={{ background: '#E8323C', color: '#F0EDE8', fontFamily: 'var(--font-manrope)', borderRadius: '2px' }}
        >
          Get started
        </a>
      </nav>

      {/* HERO */}
      <section data-landright-section="Hero" className="relative min-h-screen flex flex-col items-center justify-center px-6 md:px-12 pt-24 pb-16" style={{ background: 'radial-gradient(ellipse 80% 60% at 50% 60%, rgba(30,207,179,0.07) 0%, transparent 70%), #080C10' }}>
        {/* Teal glow behind card */}
        <div
          style={{
            position: 'absolute',
            bottom: '10%',
            left: '50%',
            transform: 'translateX(-50%)',
            width: '600px',
            height: '300px',
            background: 'radial-gradient(ellipse, rgba(30,207,179,0.18) 0%, transparent 70%)',
            pointerEvents: 'none',
            zIndex: 0,
          }}
        />

        <div className="relative z-10 flex flex-col items-center text-center max-w-5xl mx-auto">
          {/* Eyebrow */}
          <div className="flex items-center gap-2 mb-6">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#1ECFB3' }} />
            <span className="text-xs font-semibold tracking-[0.2em] uppercase" style={{ color: '#1ECFB3', fontFamily: 'var(--font-manrope)' }}>Landing Page Simulation</span>
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#1ECFB3' }} />
          </div>

          {/* Headline */}
          <h1
            style={{
              fontFamily: 'var(--font-bebas), sans-serif',
              fontSize: 'clamp(3.5rem, 10vw, 7.5rem)',
              lineHeight: 0.92,
              letterSpacing: '0.02em',
              color: '#F0EDE8',
              marginBottom: '1.5rem',
            }}
          >
            Know Which Landing Page<br />
            <span style={{ color: '#E8323C' }}>Wins</span> Before You Ship It
          </h1>

          {/* Subhead */}
          <p
            className="max-w-2xl text-base md:text-lg leading-relaxed mb-10"
            style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}
          >
            SimGym sends simulated visitors through your variants and returns real behavioral data — CTA clicks, time-on-page, drop-off patterns — so you optimize with evidence, not instinct.
          </p>

          {/* CTA */}
          <a
            href="https://example.com/signup"
            className="inline-flex items-center gap-3 px-10 py-4 text-base font-bold tracking-widest uppercase transition-all duration-200 hover:opacity-90 hover:scale-[1.02]"
            style={{
              background: '#E8323C',
              color: '#F0EDE8',
              fontFamily: 'var(--font-manrope)',
              borderRadius: '2px',
              letterSpacing: '0.12em',
              boxShadow: '0 0 40px rgba(232,50,60,0.3)',
            }}
          >
            Get started
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </a>

          {/* Dashboard mockup card */}
          <div
            className="mt-16 w-full max-w-3xl mx-auto"
            style={{
              background: '#0F1923',
              border: '1px solid rgba(30,207,179,0.15)',
              borderRadius: '6px',
              boxShadow: '0 40px 120px rgba(0,0,0,0.8), 0 0 60px rgba(30,207,179,0.08)',
              overflow: 'hidden',
            }}
          >
            {/* Card header */}
            <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#E8323C', opacity: 0.8 }} />
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#F0EDE8', opacity: 0.2 }} />
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#F0EDE8', opacity: 0.2 }} />
              </div>
              <span className="text-xs font-medium tracking-widest uppercase" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>Live Simulation — 3 Variants</span>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#1ECFB3' }} />
                <span className="text-xs" style={{ color: '#1ECFB3', fontFamily: 'var(--font-manrope)' }}>Running</span>
              </div>
            </div>

            {/* Card body */}
            <div className="p-5 md:p-6">
              {/* Visitor graph */}
              <div className="mb-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold tracking-widest uppercase" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>Simulated Sessions</span>
                  <span className="text-xs font-bold" style={{ color: '#1ECFB3', fontFamily: 'var(--font-manrope)' }}>12,480 / 15,000</span>
                </div>
                {/* Progress bar */}
                <div className="w-full h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
                  <div className="h-1.5 rounded-full" style={{ width: '83%', background: 'linear-gradient(to right, #1ECFB3, rgba(30,207,179,0.4))' }} />
                </div>
                {/* Sparkline bars */}
                <div className="flex items-end gap-1 mt-4" style={{ height: '48px' }}>
                  {[22, 35, 28, 45, 38, 52, 41, 60, 48, 55, 42, 68, 58, 72, 65, 80, 70, 76, 83].map((h, i) => (
                    <div
                      key={i}
                      className="flex-1 rounded-sm"
                      style={{
                        height: `${h}%`,
                        background: i >= 16 ? '#1ECFB3' : `rgba(30,207,179,${0.15 + i * 0.02})`,
                        transition: 'height 0.3s ease',
                      }}
                    />
                  ))}
                </div>
              </div>

              {/* Variant comparison */}
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Variant A', ctr: '3.2%', top: '1m 42s', color: '#6B7A8D', tag: null },
                  { label: 'Variant B', ctr: '5.8%', top: '2m 18s', color: '#6B7A8D', tag: null },
                  { label: 'Variant C', ctr: '8.1%', top: '3m 05s', color: '#1ECFB3', tag: 'WINNER' },
                ].map((v, i) => (
                  <div
                    key={i}
                    className="p-3 rounded"
                    style={{
                      background: v.tag ? 'rgba(30,207,179,0.06)' : 'rgba(255,255,255,0.03)',
                      border: `1px solid ${v.tag ? 'rgba(30,207,179,0.25)' : 'rgba(255,255,255,0.06)'}`,
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold" style={{ color: v.color, fontFamily: 'var(--font-manrope)' }}>{v.label}</span>
                      {v.tag && (
                        <span className="text-[9px] font-bold tracking-widest px-1.5 py-0.5" style={{ background: '#1ECFB3', color: '#080C10', borderRadius: '2px', fontFamily: 'var(--font-manrope)' }}>{v.tag}</span>
                      )}
                    </div>
                    <div className="text-xl font-bold mb-0.5" style={{ fontFamily: 'var(--font-bebas)', letterSpacing: '0.04em', color: v.tag ? '#1ECFB3' : '#F0EDE8' }}>{v.ctr}</div>
                    <div className="text-xs" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>CTR</div>
                    <div className="mt-2 text-xs" style={{ color: v.tag ? '#1ECFB3' : '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>{v.top} avg</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section data-landright-section="Features" className="relative px-6 md:px-12 py-24 md:py-32" style={{ background: '#080C10' }}>
        <div className="max-w-5xl mx-auto">
          {/* Section label */}
          <div className="flex items-center gap-4 mb-16">
            <div className="h-px flex-1" style={{ background: 'rgba(255,255,255,0.08)' }} />
            <span className="text-xs font-semibold tracking-[0.25em] uppercase" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>How It Works</span>
            <div className="h-px flex-1" style={{ background: 'rgba(255,255,255,0.08)' }} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                num: '01',
                title: 'Simulate at Scale',
                body: 'Simulate thousands of visitor sessions across multiple variants in minutes, not months.',
                accent: '#1ECFB3',
              },
              {
                num: '02',
                title: 'Capture Real Signals',
                body: 'Capture CTA click-through rates and time-on-page signals without real traffic or A/B test overhead.',
                accent: '#E8323C',
              },
              {
                num: '03',
                title: 'Export the Winner',
                body: 'Generate and test new variants automatically, then export the winner ready to deploy.',
                accent: '#1ECFB3',
              },
            ].map((f, i) => (
              <div
                key={i}
                className="p-6 md:p-8 flex flex-col"
                style={{
                  background: '#0F1923',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '4px',
                }}
              >
                <div
                  className="text-5xl md:text-6xl mb-6"
                  style={{
                    fontFamily: 'var(--font-bebas), sans-serif',
                    color: f.accent,
                    opacity: 0.5,
                    letterSpacing: '0.04em',
                    lineHeight: 1,
                  }}
                >
                  {f.num}
                </div>
                <h3
                  className="text-xl md:text-2xl mb-3"
                  style={{ fontFamily: 'var(--font-bebas), sans-serif', letterSpacing: '0.04em', color: '#F0EDE8' }}
                >
                  {f.title}
                </h3>
                <p className="text-sm leading-relaxed" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>
                  {f.body}
                </p>
                <div className="mt-6 h-px" style={{ background: `linear-gradient(to right, ${f.accent}40, transparent)` }} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* DATA SECTION */}
      <section data-landright-section="DataProof" className="relative px-6 md:px-12 py-24 md:py-32" style={{ background: 'linear-gradient(to bottom, #080C10, #0a0f14)' }}>
        <div className="max-w-5xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-20 items-center">
            {/* Left: copy */}
            <div>
              <div className="flex items-center gap-2 mb-6">
                <div className="w-1 h-8" style={{ background: '#E8323C' }} />
                <span className="text-xs font-semibold tracking-[0.2em] uppercase" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>Evidence, Not Instinct</span>
              </div>
              <h2
                className="mb-6"
                style={{
                  fontFamily: 'var(--font-bebas), sans-serif',
                  fontSize: 'clamp(2.5rem, 6vw, 4.5rem)',
                  lineHeight: 0.95,
                  letterSpacing: '0.02em',
                  color: '#F0EDE8',
                }}
              >
                Stop Guessing.<br />
                <span style={{ color: '#E8323C' }}>Start Knowing.</span>
              </h2>
              <p className="text-sm md:text-base leading-relaxed" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)', maxWidth: '420px' }}>
                Every variant decision backed by behavioral simulation data. Ship the page that converts — before a single real visitor sees it.
              </p>

              {/* Stats */}
              <div className="grid grid-cols-2 gap-6 mt-10">
                {[
                  { val: '15K+', label: 'Sessions per run' },
                  { val: '<5min', label: 'Time to results' },
                  { val: '3×', label: 'Avg CTR lift' },
                  { val: '100%', label: 'No real traffic' },
                ].map((s, i) => (
                  <div key={i}>
                    <div
                      style={{
                        fontFamily: 'var(--font-bebas), sans-serif',
                        fontSize: '2.5rem',
                        letterSpacing: '0.04em',
                        color: i % 2 === 0 ? '#1ECFB3' : '#F0EDE8',
                        lineHeight: 1,
                      }}
                    >
                      {s.val}
                    </div>
                    <div className="text-xs mt-1" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>{s.label}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right: drop-off visualization */}
            <div
              style={{
                background: '#0F1923',
                border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: '4px',
                padding: '1.5rem',
              }}
            >
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs font-semibold tracking-widest uppercase" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>Drop-off Funnel</span>
                <span className="text-xs" style={{ color: '#1ECFB3', fontFamily: 'var(--font-manrope)' }}>Variant C</span>
              </div>
              {[
                { stage: 'Page Load', pct: 100, visitors: '12,480' },
                { stage: 'Hero Scroll', pct: 78, visitors: '9,734' },
                { stage: 'Feature Read', pct: 54, visitors: '6,739' },
                { stage: 'CTA Click', pct: 31, visitors: '3,869' },
                { stage: 'Signup', pct: 18, visitors: '2,246' },
              ].map((row, i) => (
                <div key={i} className="mb-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>{row.stage}</span>
                    <span className="text-xs font-semibold" style={{ color: '#F0EDE8', fontFamily: 'var(--font-manrope)' }}>{row.visitors}</span>
                  </div>
                  <div className="w-full h-2 rounded-sm" style={{ background: 'rgba(255,255,255,0.05)' }}>
                    <div
                      className="h-2 rounded-sm"
                      style={{
                        width: `${row.pct}%`,
                        background: i === 3 ? '#E8323C' : `rgba(30,207,179,${0.3 + i * 0.1})`,
                        transition: 'width 0.5s ease',
                      }}
                    />
                  </div>
                </div>
              ))}
              <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>Overall CTR</span>
                  <span className="text-2xl font-bold" style={{ fontFamily: 'var(--font-bebas)', letterSpacing: '0.04em', color: '#1ECFB3' }}>8.1%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer data-landright-section="Footer" className="px-6 md:px-12 py-12" style={{ background: '#080C10', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-sm flex items-center justify-center" style={{ background: '#E8323C' }}>
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                <rect x="1" y="7" width="3" height="6" fill="white" />
                <rect x="5.5" y="4" width="3" height="9" fill="white" />
                <rect x="10" y="1" width="3" height="12" fill="white" />
              </svg>
            </div>
            <span style={{ fontFamily: 'var(--font-bebas), sans-serif', fontSize: '1.2rem', letterSpacing: '0.08em', color: '#F0EDE8' }}>SimGym</span>
            <span className="text-xs" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>— Landing page simulation</span>
          </div>
          <div className="text-center md:text-right">
            <p className="text-xs" style={{ color: '#6B7A8D', fontFamily: 'var(--font-manrope)' }}>© 2025 SimGym. Optimize with evidence, not instinct.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}