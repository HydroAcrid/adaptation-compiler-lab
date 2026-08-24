export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div
      aria-label="Temper"
      className={`brand ${compact ? "brand--compact" : ""}`}
    >
      <span aria-hidden="true" className="brand-mark" />
      {compact ? null : <span className="brand-word">Temper</span>}
    </div>
  );
}
