import { Fragment } from "react";
import { SyntheticBanner, TopBar } from "../components/Chrome";
import { Reveal } from "../components/Motion";

/**
 * The four-step story LifeLine tells: fragmented input → retained memory →
 * reconstructed timeline → context at the point of care.
 */
const FLOW = [
  {
    label: "Input",
    body: "Fragmented records — visits, labs, prescriptions, ED notes.",
  },
  {
    label: "Memory",
    body: "Hindsight retains each fact with provenance and time.",
  },
  {
    label: "Timeline",
    body: "The patient's story is reconstructed longitudinally.",
  },
  {
    label: "Context",
    body: "The right history surfaces at the right moment.",
  },
];

export function HomePage({
  onOpenPatient,
  onExploreMemory,
}: {
  onOpenPatient: () => void;
  onExploreMemory: () => void;
}) {
  return (
    <>
      <SyntheticBanner />
      <TopBar />

      <main className="page-shell" id="main">
        <section className="hero" aria-labelledby="hero-title">
          <Reveal>
            <h1 id="hero-title">
              Your medical history
              <br />
              <em>has a memory.</em>
            </h1>
          </Reveal>

          <Reveal delay={0.06}>
            <p className="lede">
              LifeLine connects fragmented medical records across time so important context
              doesn&apos;t disappear between visits — built on Hindsight long-term agent memory.
            </p>
          </Reveal>

          <Reveal delay={0.12}>
            <div className="hero-buttons">
              <button className="btn primary" type="button" onClick={onOpenPatient}>
                Open Demo Patient
              </button>
              <button className="btn" type="button" onClick={onExploreMemory}>
                Explore Memory <span aria-hidden="true">→</span>
              </button>
            </div>
          </Reveal>
        </section>

        <section aria-labelledby="flow-title">
          <h2 id="flow-title" className="visually-hidden">
            How LifeLine works
          </h2>
          <div className="feature-flow">
            {FLOW.map((item, i) => (
              <Fragment key={item.label}>
                {i > 0 && (
                  <div className="flow-arrow" aria-hidden="true">
                    →
                  </div>
                )}
                <Reveal className="flow-card" delay={i * 0.07}>
                  <div className="flow-card-label">{item.label}</div>
                  <p className="flow-card-body">{item.body}</p>
                </Reveal>
              </Fragment>
            ))}
          </div>
        </section>

        <p className="safety-note">
          LifeLine is a health-information assistant. It does not diagnose, prescribe, or treat.
          All demo data is synthetic. Every output requires clinician verification.
        </p>
      </main>
    </>
  );
}
