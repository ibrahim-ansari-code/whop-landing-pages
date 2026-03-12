"use client";

import {Bebas_Neue, Manrope} from 'next/font/google';

const bebas = Bebas_Neue({ subsets: ['latin'], weight: '400', variable: '--font-bebas' });
const manrope = Manrope({ subsets: ['latin'], variable: '--font-manrope' });

export default function SimGymVariant3() {
  return (
    <main className={`${bebas.variable} ${manrope.variable} bg-[#1C1A16] min-h-screen overflow-x-hidden`}>
      <style>{`
        :root {
          --font-bebas: 'Bebas Neue', sans-serif;
          --font-manrope: 'Manrope', sans-serif;
        }
        * { box-sizing: border-box; }
        body { margin: 0; }
        .font-bebas { font-family: var(--font-bebas); }
        .font-manrope { font-family: var(--font-manrope); }
        @keyframes ticker {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .ticker-track {
          animation: ticker 18s linear infinite;
          display: flex;
          width: max-content;
        }
        @keyframes floatUp {
          0% { transform: translateY(12px); opacity: 0; }
          100% { transform: translateY(0); opacity: 1; }
        }
        .float-in { animation: floatUp 0.7s ease forwards; }
        .float-in-2 { animation: floatUp 0.7s 0.15s ease both; }
        .float-in-3 { animation: floatUp 0.7s 0.3s ease both; }
        .float-in-4 { animation: floatUp 0.7s 0.45s ease both; }
        .diagonal-clip {
          clip-path: polygon(0 0, 100% 0, 100% 88%, 0 100%);
        }
        .diagonal-clip-reverse {
          clip-path: polygon(0 5%, 100% 0, 100% 100%, 0 100%);
        }
        .bar-fill {
          transition: width 1.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .amber-glow {
          box-shadow: 0 0 60px 10px rgba(245, 158, 11, 0.15);
        }
        .red-glow {
          box-shadow: 0 0 40px 4px rgba(220, 38, 38, 0.3);
        }
        .noise-overlay {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 100;
          opacity: 0.03;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
        }
        .stat-card {
          background: #252218;
          border: 1px solid #3A3520;
        }
        .feature-num {
          font-family: var(--font-bebas);
          font-size: clamp(80px, 12vw, 140px);
          line-height: 0.85;
          color: #2A2720;
          position: absolute;
          top: -10px;
          left: -8px;
          z-index: 0;
          user-select: none;
        }
      `}</style>

      {/* Noise overlay */}
      <div className="noise-overlay" aria-hidden="true" />

      {/* NAV */}
      <nav data-landright-section="Nav" className="relative z-50 flex items-center justify-between px-6 md:px-12 py-5 border-b border-[#2A2720]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-[#F59E0B] flex items-center justify-center">
            <span className="font-bebas text-[#1C1A16] text-lg leading-none">SG</span>
          </div>
          <span className="font-bebas text-[#F0EDE8] text-2xl tracking-widest">SIMGYM</span>
        </div>
        <a
          href="https://example.com/signup"
          className="font-manrope font-700 text-sm bg-[#DC2626] text-white px-5 py-2.5 uppercase tracking-widest hover:bg-[#B91C1C] transition-colors red-glow"
        >
          Get started
        </a>
      </nav>

      {/* TICKER */}
      <div className="bg-[#F59E0B] py-2 overflow-hidden" aria-hidden="true">
        <div className="ticker-track">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="flex items-center gap-8 pr-8">
              {['SIMULATE THOUSANDS OF SESSIONS', '·', 'CTA CLICK-THROUGH RATES', '·', 'TIME-ON-PAGE SIGNALS', '·', 'AUTO-GENERATE VARIANTS', '·', 'EXPORT THE WINNER', '·', 'OPTIMIZE WITH EVIDENCE', '·'].map((item, j) => (
                <span key={j} className="font-bebas text-[#1C1A16] text-sm tracking-widest whitespace-nowrap">{item}</span>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* HERO */}
      <section data-landright-section="Hero" className="relative diagonal-clip bg-[#1C1A16] pb-32 pt-16 md:pt-24 px-6 md:px-12 overflow-hidden">
        {/* Amber accent blob */}
        <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-[#F59E0B] opacity-5 rounded-full blur-3xl translate-x-1/3 -translate-y-1/3 pointer-events-none" />
        <div className="absolute bottom-0 left-1/4 w-[400px] h-[400px] bg-[#DC2626] opacity-5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-7xl mx-auto">
          {/* Label */}
          <div className="float-in inline-flex items-center gap-2 mb-6">
            <div className="w-2 h-2 bg-[#F59E0B] rounded-full" />
            <span className="font-manrope text-[#F59E0B] text-xs uppercase tracking-[0.2em] font-semibold">Landing Page Simulation</span>
          </div>

          {/* Headline — collision layout */}
          <div className="float-in-2">
            <h1 className="font-bebas text-[#F0EDE8] leading-none tracking-wide">
              <span className="block text-[clamp(56px,10vw,130px)]">KNOW WHICH</span>
              <span className="block text-[clamp(56px,10vw,130px)] text-[#F59E0B] -mt-2 md:-mt-4">LANDING PAGE</span>
              <span className="block text-[clamp(56px,10vw,130px)] -mt-2 md:-mt-4">WINS BEFORE</span>
              <span className="block text-[clamp(56px,10vw,130px)] text-[#DC2626] -mt-2 md:-mt-4">YOU SHIP IT</span>
            </h1>
          </div>

          <div className="mt-8 md:mt-10 grid md:grid-cols-2 gap-8 items-start">
            <div className="float-in-3">
              <p className="font-manrope text-[#A89F8C] text-base md:text-lg leading-relaxed max-w-lg">
                SimGym sends simulated visitors through your variants and returns real behavioral data — CTA clicks, time-on-page, drop-off patterns — so you optimize with evidence, not instinct.
              </p>
              <a
                href="https://example.com/signup"
                className="mt-8 inline-flex items-center gap-3 bg-[#DC2626] text-white font-manrope font-bold text-base px-8 py-4 uppercase tracking-widest hover:bg-[#B91C1C] transition-all red-glow group"
              >
                Get started
                <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
              </a>
            </div>

            {/* Hero stats card */}
            <div className="float-in-4 stat-card p-6 amber-glow">
              <div className="flex items-center justify-between mb-4">
                <span className="font-bebas text-[#F59E0B] text-lg tracking-widest">LIVE SIMULATION</span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                  <span className="font-manrope text-green-400 text-xs">Running</span>
                </span>
              </div>
              <div className="space-y-4">
                {[
                  { label: 'Variant A — Original', pct: 38, color: '#6B7A8D', sessions: '4,210' },
                  { label: 'Variant B — Red CTA', pct: 61, color: '#F59E0B', sessions: '4,198', winner: true },
                  { label: 'Variant C — Long copy', pct: 29, color: '#6B7A8D', sessions: '4,203' },
                ].map((v) => (
                  <div key={v.label}>
                    <div className="flex justify-between items-center mb-1.5">
                      <span className={`font-manrope text-xs font-semibold ${v.winner ? 'text-[#F59E0B]' : 'text-[#6B7A8D]'}`}>
                        {v.label} {v.winner && '★'}
                      </span>
                      <span className={`font-bebas text-xl ${v.winner ? 'text-[#F59E0B]' : 'text-[#6B7A8D]'}`}>{v.pct}%</span>
                    </div>
                    <div className="h-2 bg-[#1C1A16] rounded-none overflow-hidden">
                      <div
                        className="h-full bar-fill"
                        style={{ width: `${v.pct}%`, background: v.color }}
                      />
                    </div>
                    <div className="mt-1 font-manrope text-[10px] text-[#4A4535]">{v.sessions} sessions</div>
                  </div>
                ))}
              </div>
              <div className="mt-5 pt-4 border-t border-[#3A3520] flex justify-between">
                <div>
                  <div className="font-manrope text-[10px] text-[#4A4535] uppercase tracking-widest">Avg time on page</div>
                  <div className="font-bebas text-[#F0EDE8] text-2xl">2:34</div>
                </div>
                <div>
                  <div className="font-manrope text-[10px] text-[#4A4535] uppercase tracking-widest">Drop-off rate</div>
                  <div className="font-bebas text-[#DC2626] text-2xl">18.4%</div>
                </div>
                <div>
                  <div className="font-manrope text-[10px] text-[#4A4535] uppercase tracking-widest">Winner</div>
                  <div className="font-bebas text-[#F59E0B] text-2xl">B</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section data-landright-section="Features" className="relative bg-[#F0EDE8] diagonal-clip-reverse py-24 md:py-36 px-6 md:px-12 overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <div className="mb-12 md:mb-16">
            <span className="font-bebas text-[#DC2626] text-sm tracking-[0.3em]">HOW IT WORKS</span>
            <h2 className="font-bebas text-[#1C1A16] text-[clamp(40px,7vw,90px)] leading-none mt-1">
              THREE MOVES.<br />ONE WINNER.
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-8 md:gap-6">
            {[
              {
                num: '01',
                title: 'SIMULATE AT SCALE',
                body: 'Simulate thousands of visitor sessions across multiple variants in minutes, not months. No real traffic required.',
                accent: '#DC2626',
              },
              {
                num: '02',
                title: 'CAPTURE REAL SIGNALS',
                body: 'Capture CTA click-through rates and time-on-page signals without real traffic or A/B test overhead.',
                accent: '#F59E0B',
              },
              {
                num: '03',
                title: 'EXPORT THE WINNER',
                body: 'Generate and test new variants automatically, then export the winner ready to deploy.',
                accent: '#1C1A16',
              },
            ].map((f) => (
              <div key={f.num} className="relative pt-12 pl-4 pr-4 pb-8 border-t-4" style={{ borderColor: f.accent }}>
                <span className="feature-num" style={{ color: '#E8E4DC' }}>{f.num}</span>
                <div className="relative z-10">
                  <h3 className="font-bebas text-[#1C1A16] text-3xl md:text-4xl tracking-wide mb-3">{f.title}</h3>
                  <p className="font-manrope text-[#5A5548] text-sm md:text-base leading-relaxed">{f.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* MID CTA SECTION */}
      <section data-landright-section="MidCTA" className="relative bg-[#1C1A16] py-20 md:py-28 px-6 md:px-12 overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-[#F59E0B] opacity-5 rounded-full blur-3xl" />
        </div>
        <div className="relative z-10 max-w-5xl mx-auto">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-10">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-4">
                <div className="h-px flex-1 max-w-[60px] bg-[#F59E0B]" />
                <span className="font-manrope text-[#F59E0B] text-xs uppercase tracking-[0.2em] font-semibold">Stop guessing</span>
              </div>
              <h2 className="font-bebas text-[#F0EDE8] text-[clamp(36px,6vw,80px)] leading-none">
                OPTIMIZE WITH<br />
                <span className="text-[#F59E0B]">EVIDENCE,</span><br />
                NOT INSTINCT.
              </h2>
            </div>
            <div className="flex flex-col gap-4 items-start md:items-end">
              <div className="grid grid-cols-2 gap-3 mb-2">
                {[
                  { label: 'Sessions/run', val: '10K+' },
                  { label: 'Time to insight', val: 'Minutes' },
                  { label: 'Variants tested', val: 'Unlimited' },
                  { label: 'Real traffic needed', val: 'Zero' },
                ].map((s) => (
                  <div key={s.label} className="stat-card px-4 py-3 text-center">
                    <div className="font-bebas text-[#F59E0B] text-2xl">{s.val}</div>
                    <div className="font-manrope text-[#6B7A8D] text-[10px] uppercase tracking-widest mt-0.5">{s.label}</div>
                  </div>
                ))}
              </div>
              <a
                href="https://example.com/signup"
                className="inline-flex items-center gap-3 bg-[#F59E0B] text-[#1C1A16] font-manrope font-bold text-sm px-8 py-4 uppercase tracking-widest hover:bg-[#D97706] transition-all group"
              >
                Get started
                <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* SOCIAL PROOF / PROCESS */}
      <section data-landright-section="Process" className="bg-[#252218] py-20 md:py-28 px-6 md:px-12">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <span className="font-bebas text-[#F59E0B] text-sm tracking-[0.3em]">THE SIMGYM METHOD</span>
            <h2 className="font-bebas text-[#F0EDE8] text-[clamp(36px,6vw,72px)] leading-none mt-1">
              FROM VARIANTS TO VICTORY
            </h2>
          </div>

          <div className="relative">
            {/* Connecting line */}
            <div className="hidden md:block absolute top-10 left-0 right-0 h-px bg-[#3A3520] z-0" />
            <div className="grid md:grid-cols-4 gap-8 relative z-10">
              {[
                { step: '1', icon: '⚡', label: 'Upload Variants', desc: 'Drop in your landing page variants — HTML, URLs, or generated copy.' },
                { step: '2', icon: '🤖', label: 'Simulate Visitors', desc: 'SimGym deploys thousands of behavioral agents across every variant.' },
                { step: '3', icon: '📊', label: 'Collect Data', desc: 'CTA clicks, scroll depth, time-on-page, and drop-off patterns captured.' },
                { step: '4', icon: '🏆', label: 'Ship the Winner', desc: 'Export the top-performing variant, production-ready to deploy.' },
              ].map((s) => (
                <div key={s.step} className="flex flex-col items-center text-center">
                  <div className="w-16 h-16 bg-[#1C1A16] border-2 border-[#F59E0B] flex items-center justify-center mb-4 text-2xl">
                    {s.icon}
                  </div>
                  <div className="font-bebas text-[#F59E0B] text-xs tracking-[0.2em] mb-1">STEP {s.step}</div>
                  <h3 className="font-bebas text-[#F0EDE8] text-xl mb-2">{s.label}</h3>
                  <p className="font-manrope text-[#6B7A8D] text-sm leading-relaxed">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer data-landright-section="Footer" className="bg-[#111009] border-t border-[#2A2720] py-12 px-6 md:px-12">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-[#F59E0B] flex items-center justify-center">
              <span className="font-bebas text-[#1C1A16] text-lg leading-none">SG</span>
            </div>
            <div>
              <div className="font-bebas text-[#F0EDE8] text-xl tracking-widest">SIMGYM</div>
              <div className="font-manrope text-[#4A4535] text-xs">Landing page simulation</div>
            </div>
          </div>
          <div className="text-center">
            <p className="font-manrope text-[#4A4535] text-xs leading-relaxed max-w-sm">
              Know which landing page wins before you ship it. Simulate. Measure. Optimize.
            </p>
          </div>
          <div className="font-manrope text-[#4A4535] text-xs text-center md:text-right">
            <p>© 2025 SimGym. All rights reserved.</p>
            <p className="mt-1">Optimize with evidence, not instinct.</p>
          </div>
        </div>
      </footer>
    </main>
  );
}