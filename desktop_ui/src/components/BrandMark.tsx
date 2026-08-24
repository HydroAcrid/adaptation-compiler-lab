export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div
      aria-label="Temper"
      className={`brand ${compact ? "brand--compact" : ""}`}
    >
      <span aria-hidden="true" className="brand-mark">
        T
      </span>
      {compact ? null : (
        <span className="brand-copy">
          <span className="brand-word">Temper</span>
          <span className="brand-subtitle">behavior folio</span>
        </span>
      )}
    </div>
  );
}
