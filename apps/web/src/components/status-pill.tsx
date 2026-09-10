export function StatusPill({ value }: { value: string | null | undefined }) {
  const label = (value || "PENDING").replaceAll("_", " ");
  return <span className={`status ${(value || "pending").toLowerCase().replaceAll("_", "-")}`}>{label}</span>;
}
