"use client";

import {Archivo_Black, Source_Sans_3} from 'next/font/google';

const archivoBlack = Archivo_Black({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-archivo-black',
});

const sourceSans = Source_Sans_3({
  subsets: ['latin'],
  weight: ['300', '400', '600', '700'],
  variable: '--font-source-sans',
});

export default function SimGymVariant2() {
  return (
    <div
      className={`${archivoBlack.variable} ${sourceSans.variable} min-h-screen`}
      style={{ backgroundColor: '#F7F5F0', color: '#111111' }}
    >
      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        .font-display { font-family: var(--font-archivo-black), sans-serif; }
        .font-body { font-family: var(--font-source-sans), sans-serif; }
        .text-accent { color: #D92B2B; }
        .bg-accent { background-color: #D92B2B; }
        .text-muted { color: #888880; }
        .border-rule { border-color: #DDDDDD; }
        .scorecard-table { border-collapse: collapse; width: 100%; }
        .scorecard-table th,
        .scorecard-table td { 
          border: 1.5px solid #111111; 
          padding: 10px 14px; 
          text-align: left;
          font-family: 'Courier New', Courier, monospace;
          font-size: 13px;
        }
        .scorecard-table th {
          background-color: #111111;
          color: #F7F5F0;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          font-size: 11px;
        }
        .winning-row {
          background-color: #D92B2B;
          color: #FFFFFF;
        }
        .winning-row td {
          color: #FFFFFF;
          border-color: #D92B2B;
        }
        .losing-row td {
          color: #888880;
        }
        .cta-btn {
          display: inline-block;
          background-color: #D92B2B;
          color: #FFFFFF;
          font-family: var(--font-archivo-black), sans-serif;
          font-size: 15px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          padding: 14px 36px;
          border: none;
          cursor: pointer;
          text-decoration: none;
          transition: background-color 0.15s ease;
        }
        .cta-btn:hover { background-color: #B52222; }
        .cta-link {
          display: inline-block;
          color: #D92B2B;
          font-family: var(--font-archivo-black), sans-serif;
          font-size: 14px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          text-decoration: none;
          border-bottom: 2px solid #D92B2B;
          padding-bottom: 2px;
          transition: color 0.15s ease, border-color 0.15s ease;
        }
        .cta-link:hover { color: #B52222; border-color: #B52222; }
        .numeral {
          font-family: var(--font-archivo-black), sans-serif;
          font-size: 56px;
          line-height: 1;
          color: #DDDDDD;
          display: block;
          margin-bottom: 12px;
        }
        @media (max-width: 768px) {
          .hero-grid { grid-template-columns: 1fr !important; }
          .features-grid { grid-template-columns: 1fr !important; }
          .hero-headline { font-size: clamp(36px, 10vw, 72px) !important; }
          .scorecard-wrapper { margin-top: 40px; }
          .footer-inner { flex-direction: column !important; gap: 24px !important; align-items: flex-start !important; }
        }
      `}</style>

      {/* NAV */}
      <div data-landright-section="Nav">
        <nav
          style={{
            borderBottom: '1.5px solid #111111',
            backgroundColor: '#F7F5F0',
            position: 'sticky',
            top: 0,
            zIndex: 100,
          }}
        >
          <div
            style={{
              maxWidth: '1200px',
              margin: '0 auto',
              padding: '0 24px',
              height: '60px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
              <span
                className="font-display"
                style={{ fontSize: '20px', letterSpacing: '0.02em', color: '#111111' }}
              >
                SIM
              </span>
              <span
                className="font-display"
                style={{ fontSize: '20px', letterSpacing: '0.02em', color: '#D92B2B' }}
              >
                GYM
              </span>
            </div>
            <span
              className="font-body text-muted"
              style={{ fontSize: '12px', letterSpacing: '0.12em', textTransform: 'uppercase' }}
            >
              Landing page simulation
            </span>
          </div>
        </nav>
      </div>

      {/* HERO */}
      <div data-landright-section="Hero">
        <section
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            padding: '72px 24px 64px',
          }}
        >
          <div
            className="hero-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '64px',
              alignItems: 'start',
            }}
          >
            {/* LEFT: Headline + Subhead + CTA */}
            <div>
              <div
                style={{
                  display: 'inline-block',
                  borderTop: '3px solid #D92B2B',
                  paddingTop: '12px',
                  marginBottom: '28px',
                }}
              >
                <span
                  className="font-body text-muted"
                  style={{ fontSize: '11px', letterSpacing: '0.18em', textTransform: 'uppercase' }}
                >
                  Behavioral Intelligence
                </span>
              </div>

              <h1
                className="font-display hero-headline"
                style={{
                  fontSize: 'clamp(40px, 6vw, 80px)',
                  lineHeight: '1.0',
                  letterSpacing: '-0.01em',
                  color: '#111111',
                  marginBottom: '28px',
                }}
              >
                Know Which Landing Page Wins Before You Ship It
              </h1>

              <p
                className="font-body"
                style={{
                  fontSize: '17px',
                  lineHeight: '1.65',
                  color: '#444440',
                  marginBottom: '40px',
                  maxWidth: '460px',
                }}
              >
                SimGym sends simulated visitors through your variants and returns real behavioral data — CTA clicks, time-on-page, drop-off patterns — so you optimize with evidence, not instinct.
              </p>

              <a href="https://example.com/signup" className="cta-btn">
                Get started
              </a>

              <div
                style={{
                  marginTop: '40px',
                  paddingTop: '28px',
                  borderTop: '1px solid #DDDDDD',
                  display: 'flex',
                  gap: '32px',
                }}
              >
                {[
                  { val: '10K+', label: 'Sessions / run' },
                  { val: '<5 min', label: 'Time to results' },
                  { val: '100%', label: 'No real traffic' },
                ].map((stat) => (
                  <div key={stat.label}>
                    <div
                      className="font-display"
                      style={{ fontSize: '22px', color: '#111111' }}
                    >
                      {stat.val}
                    </div>
                    <div
                      className="font-body text-muted"
                      style={{ fontSize: '11px', letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: '2px' }}
                    >
                      {stat.label}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* RIGHT: Scorecard Table */}
            <div className="scorecard-wrapper">
              <div
                style={{
                  border: '1.5px solid #111111',
                  backgroundColor: '#FFFFFF',
                }}
              >
                {/* Table header bar */}
                <div
                  style={{
                    borderBottom: '1.5px solid #111111',
                    padding: '12px 16px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <span
                    className="font-body"
                    style={{
                      fontSize: '11px',
                      letterSpacing: '0.14em',
                      textTransform: 'uppercase',
                      color: '#888880',
                    }}
                  >
                    Simulation Report — Run #0047
                  </span>
                  <span
                    style={{
                      backgroundColor: '#D92B2B',
                      color: '#FFFFFF',
                      fontSize: '10px',
                      fontFamily: 'Courier New, monospace',
                      padding: '2px 8px',
                      letterSpacing: '0.1em',
                    }}
                  >
                    COMPLETE
                  </span>
                </div>

                <div style={{ padding: '0' }}>
                  <table className="scorecard-table">
                    <thead>
                      <tr>
                        <th>VARIANT</th>
                        <th>SESSIONS</th>
                        <th>CTA CTR</th>
                        <th>AVG TIME</th>
                        <th>DROP-OFF</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="winning-row">
                        <td>▲ VAR B</td>
                        <td>5,000</td>
                        <td>12.4%</td>
                        <td>2m 41s</td>
                        <td>31%</td>
                      </tr>
                      <tr className="losing-row">
                        <td>VAR A</td>
                        <td>5,000</td>
                        <td>7.1%</td>
                        <td>1m 18s</td>
                        <td>58%</td>
                      </tr>
                      <tr className="losing-row">
                        <td>VAR C</td>
                        <td>5,000</td>
                        <td>8.9%</td>
                        <td>1m 52s</td>
                        <td>49%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Confidence bar */}
                <div
                  style={{
                    borderTop: '1.5px solid #111111',
                    padding: '14px 16px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: '8px',
                    }}
                  >
                    <span
                      className="font-body"
                      style={{ fontSize: '11px', letterSpacing: '0.1em', textTransform: 'uppercase', color: '#888880' }}
                    >
                      Statistical confidence
                    </span>
                    <span
                      style={{ fontFamily: 'Courier New, monospace', fontSize: '13px', color: '#111111', fontWeight: 700 }}
                    >
                      97.3%
                    </span>
                  </div>
                  <div style={{ height: '6px', backgroundColor: '#DDDDDD' }}>
                    <div
                      style={{
                        height: '100%',
                        width: '97.3%',
                        backgroundColor: '#D92B2B',
                      }}
                    />
                  </div>
                </div>

                {/* Recommendation */}
                <div
                  style={{
                    borderTop: '1.5px solid #111111',
                    padding: '14px 16px',
                    backgroundColor: '#F7F5F0',
                  }}
                >
                  <span
                    className="font-body"
                    style={{ fontSize: '12px', color: '#444440', lineHeight: '1.5' }}
                  >
                    <strong style={{ color: '#D92B2B' }}>Recommendation:</strong> Deploy Variant B. +74.6% lift in CTA CTR over control.
                  </span>
                </div>
              </div>

              {/* Caption */}
              <p
                className="font-body text-muted"
                style={{ fontSize: '11px', marginTop: '10px', letterSpacing: '0.06em' }}
              >
                Simulated output — 15,000 sessions across 3 variants, completed in 4 minutes.
              </p>
            </div>
          </div>
        </section>
      </div>

      {/* DIVIDER */}
      <div
        style={{
          borderTop: '1.5px solid #111111',
          maxWidth: '1200px',
          margin: '0 auto',
        }}
      />

      {/* FEATURES */}
      <div data-landright-section="Features">
        <section
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            padding: '72px 24px',
          }}
        >
          <div
            className="features-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '0',
              borderTop: '1.5px solid #111111',
              borderLeft: '1.5px solid #111111',
            }}
          >
            {[
              {
                num: '01',
                title: 'Simulate at Scale',
                body: 'Run thousands of visitor sessions across multiple variants in minutes, not months. No traffic required.',
              },
              {
                num: '02',
                title: 'Capture Real Signals',
                body: 'Measure CTA click-through rates and time-on-page without A/B test overhead or waiting for organic traffic.',
              },
              {
                num: '03',
                title: 'Export the Winner',
                body: 'Generate and test new variants automatically, then export the winning page ready to deploy immediately.',
              },
            ].map((feature) => (
              <div
                key={feature.num}
                style={{
                  borderRight: '1.5px solid #111111',
                  borderBottom: '1.5px solid #111111',
                  padding: '36px 32px',
                  backgroundColor: '#FFFFFF',
                }}
              >
                <span className="numeral">{feature.num}</span>
                <h3
                  className="font-display"
                  style={{
                    fontSize: '20px',
                    letterSpacing: '0.01em',
                    color: '#111111',
                    marginBottom: '14px',
                  }}
                >
                  {feature.title}
                </h3>
                <p
                  className="font-body"
                  style={{
                    fontSize: '15px',
                    lineHeight: '1.65',
                    color: '#444440',
                  }}
                >
                  {feature.body}
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* DIVIDER */}
      <div
        style={{
          borderTop: '1.5px solid #111111',
          maxWidth: '1200px',
          margin: '0 auto',
        }}
      />

      {/* HOW IT WORKS */}
      <div data-landright-section="HowItWorks">
        <section
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            padding: '72px 24px',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '48px',
              alignItems: 'center',
            }}
          >
            <div>
              <div
                style={{
                  borderTop: '3px solid #D92B2B',
                  paddingTop: '12px',
                  marginBottom: '24px',
                  display: 'inline-block',
                }}
              >
                <span
                  className="font-body text-muted"
                  style={{ fontSize: '11px', letterSpacing: '0.18em', textTransform: 'uppercase' }}
                >
                  The Method
                </span>
              </div>
              <h2
                className="font-display"
                style={{
                  fontSize: 'clamp(28px, 4vw, 48px)',
                  lineHeight: '1.05',
                  color: '#111111',
                  marginBottom: '20px',
                }}
              >
                Evidence Replaces Instinct
              </h2>
              <p
                className="font-body"
                style={{
                  fontSize: '16px',
                  lineHeight: '1.7',
                  color: '#444440',
                }}
              >
                Traditional A/B testing demands real traffic, weeks of runtime, and statistical patience. SimGym compresses that cycle into minutes by running synthetic behavioral models against your variants — giving you directional data before a single real visitor arrives.
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
              {[
                { step: '1', label: 'Upload your variants', desc: 'Paste URLs or upload HTML for each page variant you want to test.' },
                { step: '2', label: 'Configure the simulation', desc: 'Set session count, visitor personas, and behavioral parameters.' },
                { step: '3', label: 'Receive behavioral data', desc: 'Get CTA CTR, time-on-page, and drop-off heatmaps within minutes.' },
                { step: '4', label: 'Deploy the winner', desc: 'Export the top-performing variant, production-ready.' },
              ].map((item, i) => (
                <div
                  key={item.step}
                  style={{
                    display: 'flex',
                    gap: '20px',
                    padding: '20px 0',
                    borderBottom: i < 3 ? '1px solid #DDDDDD' : 'none',
                    alignItems: 'flex-start',
                  }}
                >
                  <div
                    style={{
                      width: '32px',
                      height: '32px',
                      border: '1.5px solid #111111',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      fontFamily: 'Courier New, monospace',
                      fontSize: '13px',
                      fontWeight: 700,
                      color: '#111111',
                    }}
                  >
                    {item.step}
                  </div>
                  <div>
                    <div
                      className="font-display"
                      style={{ fontSize: '15px', color: '#111111', marginBottom: '4px' }}
                    >
                      {item.label}
                    </div>
                    <div
                      className="font-body text-muted"
                      style={{ fontSize: '14px', lineHeight: '1.5' }}
                    >
                      {item.desc}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      {/* FOOTER */}
      <div data-landright-section="Footer">
        <footer
          style={{
            borderTop: '1.5px solid #111111',
            backgroundColor: '#111111',
          }}
        >
          <div
            style={{
              maxWidth: '1200px',
              margin: '0 auto',
              padding: '48px 24px',
            }}
          >
            <div
              className="footer-inner"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '8px' }}>
                  <span
                    className="font-display"
                    style={{ fontSize: '22px', letterSpacing: '0.02em', color: '#F7F5F0' }}
                  >
                    SIM
                  </span>
                  <span
                    className="font-display"
                    style={{ fontSize: '22px', letterSpacing: '0.02em', color: '#D92B2B' }}
                  >
                    GYM
                  </span>
                </div>
                <p
                  className="font-body"
                  style={{ fontSize: '13px', color: '#888880', letterSpacing: '0.06em' }}
                >
                  Landing page simulation
                </p>
                <p
                  className="font-body"
                  style={{ fontSize: '12px', color: '#555550', marginTop: '16px' }}
                >
                  © 2025 SimGym. All rights reserved.
                </p>
              </div>

              <div style={{ textAlign: 'right' }}>
                <p
                  className="font-body"
                  style={{
                    fontSize: '14px',
                    color: '#888880',
                    marginBottom: '20px',
                    maxWidth: '280px',
                    lineHeight: '1.6',
                  }}
                >
                  Stop guessing. Start shipping pages that are already proven to convert.
                </p>
                <a href="https://example.com/signup" className="cta-link" style={{ color: '#D92B2B', borderColor: '#D92B2B' }}>
                  Get started →
                </a>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}