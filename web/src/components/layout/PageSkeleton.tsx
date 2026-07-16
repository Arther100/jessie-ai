export function PageSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="space-y-2">
        <div className="h-8 w-48 rounded-lg bg-gray-200 dark:bg-gray-800" />
        <div className="h-4 w-72 rounded bg-gray-100 dark:bg-gray-800/70" />
      </div>
      <div className="h-40 rounded-xl bg-gray-100 dark:bg-gray-800/70" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 h-56 rounded-xl bg-gray-100 dark:bg-gray-800/70" />
        <div className="h-56 rounded-xl bg-gray-100 dark:bg-gray-800/70" />
      </div>
    </div>
  );
}
