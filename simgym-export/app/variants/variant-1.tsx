"use client";

import {Bebas_Neue, Manrope} from 'next/font/google';

const bebas = Bebas_Neue({ subsets: ['latin'], weight: '400', variable: '--font-bebas' });
const manrope = Manrope({ subsets: ['latin'], variable: '--font-manrope' });

export default function SimGymV1() {
  return (
    <div className={`${bebas.variable} ${manrope.variable} min-h-screen bg-[#080C10] text-[#F0EDE8] relative overflow-x-hidden`} style={{ fontFamily: 'var(--font-manrope)' }}>
      {/* Film grain overlay */}
      <svg className="fixed inset-0 w-full h-full pointer-events-none z-50 opacity-[0.035]" style={{ mixBlendMode: 'overlay' }}>
        <filter id="grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="4" stitchTiles="stitch" />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#grain)" />
      </svg>

      {/* Teal radial glow behind dashboard */}
      <div className="absolute left-1/2 -translate-x-1/2 top-[55%] w-[900px] h-[600px] rounded-full pointer-events-none" style={{ background: 'radial-gradient(ellipse at center, rgba(30,207,179,0.13) 0%, rgba(30,207,179,0.04) 40%, transparent 70%)', filter: 'blur(40px)' }} />

      {/* Deep teal-to-black gradient mesh */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse 80% 60% at 50% 0%, rgba(14,40,50,0.7) 0%, transparent 70%)' }} />

      {/* NAV */}
      <nav data-landright-section="Nav" className="relative z-10 flex items-center justify-between px-6 md:px-12 lg:px-20 py-6">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-sm flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #1ECFB3 0%, #0a8a78 100%)' }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="7" width="3" height="6" fill="#080C10" />
              <rect x="5.5" y="4" width="3" height="9" fill="#080C10" />
              <rect x="10" y="1" width="3" height="12" fill="#080C10" />
            </svg>
          </div>
          <span style={{ fontFamily: 'var(--font-bebas)', letterSpacing: '0.08em' }} className="text-2xl text-[#F0EDE8]">SimGym</span>
        </div>
        <a
          href="https://example.com/signup"
          className="hidden md:inline-flex items-center gap-2 px-5 py-2 text-sm font-semibold tracking-wide transition-all duration-200 hover:opacity-90"
          style={{ background: '#E8323C', color: '#F0EDE8', fontFamily: 'var(--font-manrope)', letterSpacing: '0.04em' }}
        >
          Get started
        </a>
      </nav>

      {/* HERO */}
      <section data-landright-section="Hero" className="relative z-10 flex flex-col items-center text-center px-6 md:px-12 pt-12 md:pt-16 pb-0">
        <div className="inline-flex items-center gap-2 px-3 py-1 mb-8 rounded-full border border-[#1ECFB3]/30 bg-[#1ECFB3]/5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#1ECFB3] animate-pulse" />
          <span className="text-[#1ECFB3] text-xs font-semibold tracking-widest uppercase" style={{ fontFamily: 'var(--font-manrope)' }}>Landing page simulation</span>
        </div>

        <h1
          style={{ fontFamily: 'var(--font-bebas)', letterSpacing: '0.02em', lineHeight: '0.92' }}
          className="text-[clamp(52px,10vw,108px)] text-[#F0EDE8] max-w-5xl mb-6"
        >
          Know Which Landing Page<br />
          <span style={{ color: '#1ECFB3' }}>Wins</span> Before You Ship It
        </h1>

        <p className="text-[#6B7A8D] text-base md:text-lg max-w-2xl mb-10 leading-relaxed" style={{ fontFamily: 'var(--font-manrope)' }}>
          SimGym sends simulated visitors through your variants and returns real behavioral data — CTA clicks, time-on-page, drop-off patterns — so you optimize with evidence, not instinct.
        </p>

        <a
          href="https://example.com/signup"
          className="inline-flex items-center gap-3 px-8 py-4 text-base font-bold tracking-widest uppercase transition-all duration-200 hover:opacity-90 hover:scale-[1.02] active:scale-[0.98]"
          style={{ background: '#E8323C', color: '#F0EDE8', fontFamily: 'var(--font-manrope)', letterSpacing: '0.1em', boxShadow: '0 0 40px rgba(232,50,60,0.25)' }}
        >
          Get started
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </a>

        {/* Dashboard mockup card */}
        <div className="relative mt-16 w-full max-w-4xl mx-auto">
          {/* Glow ring */}
          <div className="absolute -inset-px rounded-xl pointer-events-none" style={{ background: 'linear-gradient(135deg, rgba(30,207,179,0.3) 0%, rgba(232,50,60,0.15) 50%, transparent 100%)', borderRadius: '12px' }} />
          <div
            className="relative rounded-xl overflow-hidden"
            style={{
              background: '#0F1923',
              border: '1px solid rgba(30,207,179,0.15)',
              boxShadow: '0 40px 120px rgba(0,0,0,0.8), 0 0 60px rgba(30,207,179,0.08)'
            }}
          >
            {/* Card header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[#E8323C]/70" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/40" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#1ECFB3]/40" />
              </div>
              <span className="text-[#6B7A8D] text-xs tracking-widest uppercase" style={{ fontFamily: 'var(--font-manrope)' }}>Live Simulation — Run #2847</span>
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#1ECFB3] animate-pulse" />
                <span className="text-[#1ECFB3] text-xs font-semibold" style={{ fontFamily: 'var(--font-manrope)' }}>Running</span>
              </div>
            </div>

            <div className="p-5 md:p-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Visitor activity graph */}
              <div className="md:col-span-2 rounded-lg p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div className="flex items-center justify-between mb-4">
                  <span className="text-[#6B7A8D] text-xs uppercase tracking-widest" style={{ fontFamily: 'var(--font-manrope)' }}>Visitor Sessions / Minute</span>
                  <span className="text-[#1ECFB3] text-xs font-bold" style={{ fontFamily: 'var(--font-manrope)' }}>+12,400 simulated</span>
                </div>
                {/* SVG chart */}
                <svg viewBox="0 0 400 100" className="w-full h-24" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="chartGradA" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#1ECFB3" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#1ECFB3" stopOpacity="0" />
                    </linearGradient>
                    <linearGradient id="chartGradB" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#E8323C" stopOpacity="0.25" />
                      <stop offset="100%" stopColor="#E8323C" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  {/* Variant A area */}
                  <path d="M0,80 C30,75 60,55 90,45 C120,35 150,50 180,38 C210,26 240,30 270,20 C300,10 330,18 360,12 C380,8 400,10 400,10 L400,100 L0,100 Z" fill="url(#chartGradA)" />
                  <path d="M0,80 C30,75 60,55 90,45 C120,35 150,50 180,38 C210,26 240,30 270,20 C300,10 330,18 360,12 C380,8 400,10 400,10" fill="none" stroke="#1ECFB3" strokeWidth="1.5" />
                  {/* Variant B area */}
                  <path d="M0,85 C30,82 60,70 90,65 C120,60 150,68 180,58 C210,48 240,55 270,45 C300,35 330,40 360,35 C380,32 400,30 400,30 L400,100 L0,100 Z" fill="url(#chartGradB)" />
                  <path d="M0,85 C30,82 60,70 90,65 C120,60 150,68 180,58 C210,48 240,55 270,45 C300,35 330,40 360,35 C380,32 400,30 400,30" fill="none" stroke="#E8323C" strokeWidth="1.5" strokeDasharray="4 2" />
                  {/* Pulse dot */}
                  <circle cx="400" cy="10" r="3" fill="#1ECFB3" />
                  <circle cx="400" cy="10" r="6" fill="#1ECFB3" fillOpacity="0.2" />
                </svg>
                <div className="flex items-center gap-4 mt-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 bg-[#1ECFB3]" />
                    <span className="text-[#6B7A8D] text-xs" style={{ fontFamily: 'var(--font-manrope)' }}>Variant A</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 bg-[#E8323C]" style={{ backgroundImage: 'repeating-linear-gradient(90deg, #E8323C 0, #E8323C 4px, transparent 4px, transparent 6px)' }} />
                    <span className="text-[#6B7A8D] text-xs" style={{ fontFamily: 'var(--font-manrope)' }}>Variant B</span>
                  </div>
                </div>
              </div>

              {/* Metrics column */}
              <div className="flex flex-col gap-3">
                {[
                  { label: 'CTA Click-Through', a: '18.4%', b: '11.2%', winner: 'a' },
                  { label: 'Avg. Time on Page', a: '2m 41s', b: '1m 58s', winner: 'a' },
                  { label: 'Drop-off Rate', a: '34%', b: '52%', winner: 'a' },
                ].map((metric) => (
                  <div key={metric.label} className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div className="text-[#6B7A8D] text-[10px] uppercase tracking-widest mb-2" style={{ fontFamily: 'var(--font-manrope)' }}>{metric.label}</div>
                    <div className="flex items-center justify-between">
                      <div className="text-center">
                        <div className="text-[#1ECFB3] text-sm font-bold" style={{ fontFamily: 'var(--font-manrope)' }}>{metric.a}</div>
                        <div className="text-[#6B7A8D] text-[10px]" style={{ fontFamily: 'var(--font-manrope)' }}>A</div>
                      </div>
                      <div className="text-[#6B7A8D] text-xs">vs</div>
                      <div className="text-center">
                        <div className="text-[#F0EDE8]/50 text-sm font-bold" style={{ fontFamily: 'var(--font-manrope)' }}>{metric.b}</div>
                        <div className="text-[#6B7A8D] text-[10px]" style={{ fontFamily: 'var(--font-manrope)' }}>B</div>
                      </div>
                    </div>
                  </div>
                ))}
                <div className="rounded-lg p-3 flex items-center gap-2" style={{ background: 'rgba(30,207,179,0.08)', border: '1px solid rgba(30,207,179,0.2)' }}>
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M7 1l1.5 4h4l-3.2 2.4 1.2 4L7 9 3.5 11.4l1.2-4L1.5 5h4z" fill="#1ECFB3" />
                  </svg>
                  <span className="text-[#1ECFB3] text-xs font-bold" style={{ fontFamily: 'var(--font-manrope)' }}>Variant A wins</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section data-landright-section="Features" className="relative z-10 px-6 md:px-12 lg:px-20 pt-24 pb-20">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center gap-3 mb-12">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent to-[#1ECFB3]/30" />
            <span className="text-[#1ECFB3] text-xs uppercase tracking-[0.3em] font-semibold" style={{ fontFamily: 'var(--font-manrope)' }}>How it works</span>
            <div className="h-px flex-1 bg-gradient-to-l from-transparent to-[#1ECFB3]/30" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                num: '01',
                title: 'Simulate at Scale',
                body: 'Run thousands of visitor sessions across multiple variants in minutes, not months. No real traffic required.',
                accent: '#1ECFB3',
              },
              {
                num: '02',
                title: 'Capture Real Signals',
                body: 'Measure CTA click-through rates and time-on-page without A/B test overhead or waiting for organic traffic.',
                accent: '#E8323C',
              },
              {
                num: '03',
                title: 'Export the Winner',
                body: 'Generate and test new variants automatically, then export the winning page ready to deploy — no guesswork.',
                accent: '#1ECFB3',
              },
            ].map((f) => (
              <div
                key={f.num}
                className="rounded-xl p-6 relative overflow-hidden group"
                style={{ background: '#0F1923', border: '1px solid rgba(255,255,255,0.06)' }}
              >
                <div className="absolute top-0 left-0 right-0 h-px" style={{ background: `linear-gradient(90deg, transparent, ${f.accent}40, transparent)` }} />
                <div
                  className="text-5xl mb-4 font-bold"
                  style={{ fontFamily: 'var(--font-bebas)', color: f.accent, opacity: 0.25, letterSpacing: '0.05em' }}
                >
                  {f.num}
                </div>
                <h3
                  className="text-xl mb-3"
                  style={{ fontFamily: 'var(--font-bebas)', letterSpacing: '0.05em', color: '#F0EDE8' }}
                >
                  {f.title}
                </h3>
                <p className="text-[#6B7A8D] text-sm leading-relaxed" style={{ fontFamily: 'var(--font-manrope)' }}>
                  {f.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* STATS BAR */}
      <section data-landright-section="Stats" className="relative z-10 px-6 md:px-12 lg:px-20 py-12" style={{ borderTop: '1px solid rgba(255,255,255,0.05)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
          {[
            { value: '12,000+', label: 'Sessions per run' },
            { value: '<5 min', label: 'Time to results' },
            { value: '3×', label: 'Faster than A/B tests' },
            { value: '100%', label: 'Evidence-based' },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <div
                className="text-3xl md:text-4xl mb-1"
                style={{ fontFamily: 'var(--font-bebas)', color: '#1ECFB3', letterSpacing: '0.05em' }}
              >
                {stat.value}
              </div>
              <div className="text-[#6B7A8D] text-xs uppercase tracking-widest" style={{ fontFamily: 'var(--font-manrope)' }}>
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* FOOTER */}
      <footer data-landright-section="Footer" className="relative z-10 px-6 md:px-12 lg:px-20 py-10">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-sm flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #1ECFB3 0%, #0a8a78 100%)' }}>
              <svg width="10" height="10" viewBox="0 0 14 14" fill="none">
                <rect x="1" y="7" width="3" height="6" fill="#080C10" />
                <rect x="5.5" y="4" width="3" height="9" fill="#080C10" />
                <rect x="10" y="1" width="3" height="12" fill="#080C10" />
              </svg>
            </div>
            <span style={{ fontFamily: 'var(--font-bebas)', letterSpacing: '0.08em' }} className="text-lg text-[#F0EDE8]">SimGym</span>
          </div>
          <p className="text-[#6B7A8D] text-xs text-center" style={{ fontFamily: 'var(--font-manrope)' }}>
            Landing page simulation — optimize with evidence, not instinct.
          </p>
          <p className="text-[#6B7A8D] text-xs" style={{ fontFamily: 'var(--font-manrope)' }}>
            © 2025 SimGym. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}