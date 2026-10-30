import { Check, Copy } from 'lucide-react';
import { useCopy } from '../hooks/motion';

/** Small secondary copy button for the dark dashboard surface. */
export function CopyButtonInline({ text, label = 'Copy' }: { text: string; label?: string }) {
  const { copied, copy } = useCopy();
  return (
    <button type="button" onClick={() => copy(text)} className="btn-secondary h-7 px-2 text-[12px]" aria-label={copied ? 'Copied' : label}>
      {copied ? <Check className="h-3.5 w-3.5 text-allow" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      <span aria-live="polite">{copied ? 'Copied' : label}</span>
    </button>
  );
}
