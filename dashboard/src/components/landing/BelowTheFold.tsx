import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import type { ApiState } from '../../hooks/useApi';
import type { Evaluation } from '../../api/types';
import { EvidenceSection, GeneralisationSection } from './Evidence';
import Bento from './Bento';
import QuickStart from './QuickStart';
import Trust from './Trust';
import { REPO_URL } from './SiteChrome';

function FinalCta() {
  return (
    <section aria-labelledby="cta-h" className="border-t border-line">
      <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="grid items-end gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <h2 id="cta-h" className="h-section max-w-[18ch] sm:text-[3rem]">
            Put a gate in front of your GraphQL API.
          </h2>
          <div className="flex flex-wrap gap-2.5 lg:justify-end">
            <a href="#start" className="btn-primary btn-lg">
              Run it yourself <ArrowRight className="h-4 w-4" aria-hidden />
            </a>
            <Link to="/app" className="btn-secondary btn-lg">
              Open the dashboard
            </Link>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="btn-ghost btn-lg">
              GitHub
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

/** Landing sections below the hero, split into their own chunk (see pages/Landing.tsx). */
export default function BelowTheFold({ evaluation }: { evaluation: ApiState<Evaluation> }) {
  // These sections load after first paint, so a deep link such as /#how cannot be honoured by the browser alone.
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (!id) return;
    const go = () => document.getElementById(id)?.scrollIntoView({ behavior: 'instant' });
    go();
    const settle = window.setTimeout(go, 400); // charts and web fonts shift the layout slightly after mount
    return () => window.clearTimeout(settle);
  }, []);

  return (
    <>
      <EvidenceSection state={evaluation} />
      <Bento />
      <GeneralisationSection state={evaluation} />
      <QuickStart />
      <Trust />
      <FinalCta />
    </>
  );
}
