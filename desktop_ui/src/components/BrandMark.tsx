export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div
      aria-label="Temper"
      className={`brand ${compact ? "brand--compact" : ""}`}
    >
      <span aria-hidden="true" className="brand-mark">
        <span />
        <span />
        <span />
      </span>
      {compact ? null : <span className="brand-word">temper</span>}
    </div>
  );
}
