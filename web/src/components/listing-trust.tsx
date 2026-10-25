type SellerClaim = { label: string; value: string };
export type VerifiedEvidence = { id?: string; label: string; summary: string; source: string; checked_at: string; scope: string };

export function ListingTrust({ claims, evidence = [] }: { claims: SellerClaim[]; evidence?: VerifiedEvidence[] }) {
  const validEvidence = evidence.filter((item) => item.label.trim() && item.summary.trim() && item.source.trim() && item.scope.trim() && Number.isFinite(Date.parse(item.checked_at)));
  return <section className="detail-summary listing-trust" aria-labelledby="listing-trust-heading">
    <h2 id="listing-trust-heading">Проверено</h2>
    {validEvidence.length ? <ul aria-label="Подтверждённые сведения">{validEvidence.map((item, index) => <li key={item.id || `${item.label}-${index}`}>
      <strong>{item.label}</strong> · {item.summary} · область: {item.scope} · источник: {item.source} · дата проверки: {new Date(item.checked_at).toLocaleDateString("ru-BY")}
    </li>)}</ul> : <p className="muted">Для этого объявления нет сведений, подтверждённых независимым источником. Наличие VIN само по себе не подтверждает историю автомобиля или число владельцев.</p>}
    {claims.length > 0 && <div className="seller-claims"><h3>Указано продавцом</h3><ul>{claims.map((claim) => <li key={claim.label}>{claim.label}: {claim.value}</li>)}</ul></div>}
  </section>;
}
