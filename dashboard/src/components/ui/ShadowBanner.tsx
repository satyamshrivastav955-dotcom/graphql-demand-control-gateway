/** Persistent notice shown when the gateway records decisions without enforcing them. */
export function ShadowBanner({ className = '' }: { className?: string }) {
  return (
    <div role="status" className={`flex items-center gap-2.5 border-b border-throttle/25 bg-throttle/[0.07] px-4 py-1.5 text-[12.5px] text-throttle lg:px-6 ${className}`}>
      <span className="h-1.5 w-1.5 shrink-0 rounded-full border-[1.5px] border-throttle" aria-hidden />
      <p>
        <span className="font-semibold">Shadow mode.</span>{' '}
        <span className="text-throttle/90">
          Decisions are recorded but not enforced: every operation is forwarded. &ldquo;Would block&rdquo; and &ldquo;would throttle&rdquo; show what enforcement would have done.
        </span>
      </p>
    </div>
  );
}
