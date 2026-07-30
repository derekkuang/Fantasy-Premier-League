// Next renders this automatically while the async page above is awaiting its data
// (App Router wires it up via Suspense — you don't import it anywhere). A few pulsing
// grey blocks so the page never flashes blank.

function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-black/5 dark:bg-white/10 ${className}`} />;
}

export default function Loading() {
  return (
    <main className="mx-auto flex max-w-md flex-col gap-5 px-4 py-8">
      <Block className="h-6 w-40" />
      <Block className="h-28 w-full" />
      <Block className="h-16 w-full" />
      <Block className="h-16 w-full" />
      <Block className="h-72 w-full" />
    </main>
  );
}
