export default function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && (
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-500">{description}</p>
        )}
      </div>
      {actions}
    </div>
  );
}