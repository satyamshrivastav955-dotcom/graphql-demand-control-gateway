import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Menu, X } from 'lucide-react';
import { Wordmark } from '../Brand';

export const REPO_URL = 'https://github.com/satyamshrivastav955-dotcom/GraphQL-Sentinel';
export const AUTHOR_URL = 'https://github.com/satyamshrivastav955-dotcom';
export const doc = (path: string) => `${REPO_URL}/blob/main/${path}`;

const LINKS = [
  { href: '#demo', label: 'See it decide' },
  { href: '#evidence', label: 'Evidence' },
  { href: '#how', label: 'How it works' },
  { href: '#start', label: 'Run it' },
];

export function Nav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 4);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);
  return (
    <header className={`sticky top-0 z-40 transition-[background-color,border-color,backdrop-filter] duration-200 ${scrolled || open ? 'border-b border-line bg-ink-950/75 backdrop-blur-md' : 'border-b border-transparent'}`}>
      <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-6 px-5 sm:px-8">
        <Wordmark />
        <nav aria-label="Primary" className="hidden items-center gap-1 whitespace-nowrap text-[13.5px] text-ink-300 lg:flex">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} className="rounded-md px-3 py-1.5 transition-colors hover:bg-white/[0.06] hover:text-ink-50">
              {l.label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1.5">
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="hidden items-center gap-1 rounded-md px-3 py-1.5 text-[13.5px] text-ink-300 transition-colors hover:bg-white/[0.06] hover:text-ink-50 sm:inline-flex">
            GitHub <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
          </a>
          <Link to="/app" className="btn-primary hidden whitespace-nowrap sm:inline-flex">
            Open dashboard
          </Link>
          <button
            type="button"
            className="btn-ghost h-9 w-9 px-0 lg:hidden"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            aria-controls="mobile-menu"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>
      {open && (
        <nav id="mobile-menu" aria-label="Mobile" className="border-t border-line bg-ink-950 px-5 pb-5 pt-2 lg:hidden">
          {[...LINKS, { href: REPO_URL, label: 'GitHub' }].map((l) => (
            <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="flex min-h-[48px] items-center border-b border-line-faint text-[15px] text-ink-100">
              {l.label}
            </a>
          ))}
          <Link to="/app" className="btn-primary btn-lg mt-4 w-full">
            Open dashboard
          </Link>
        </nav>
      )}
    </header>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto grid max-w-[1200px] gap-10 px-5 py-12 sm:px-8 md:grid-cols-[1.5fr_1fr_1fr_1fr]">
        <div>
          <Wordmark />
          <p className="mt-4 max-w-xs text-[13.5px] leading-relaxed text-ink-400">An open-source security gateway that reads the GraphQL operation. v1.0 pre-release, MIT licensed, no tracking.</p>
        </div>
        <FooterCol title="Project" links={[['GitHub', REPO_URL], ['Licence (MIT)', doc('LICENSE')], ['Changelog', doc('CHANGELOG.md')]]} />
        <FooterCol title="Documentation" links={[['Architecture', doc('docs/architecture.md')], ['Threat model', doc('docs/threat-model.md')], ['Evaluation', doc('docs/evaluation.md')], ['Deployment', doc('docs/deployment.md')]]} />
        <FooterCol title="Product" links={[['Dashboard', '/app'], ['Security policy', doc('SECURITY.md')], ['Author', AUTHOR_URL]]} />
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-[1200px] px-5 py-4 text-[12.5px] text-ink-400 sm:px-8">Copyright 2025-2026 Satyam Santosh Shrivastav. Not a WAF and not an authorisation layer; see the threat model.</p>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <h2 className="text-[13px] font-medium text-ink-50">{title}</h2>
      <ul className="mt-3 space-y-0.5">
        {links.map(([label, href]) => (
          <li key={label}>
            {href.startsWith('/') ? (
              <Link to={href} className="inline-flex min-h-[28px] items-center text-[13.5px] text-ink-400 hover:text-ink-50">
                {label}
              </Link>
            ) : (
              <a href={href} target="_blank" rel="noreferrer" className="inline-flex min-h-[28px] items-center text-[13.5px] text-ink-400 hover:text-ink-50">
                {label}
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
