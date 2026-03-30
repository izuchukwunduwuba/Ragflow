type ConfidenceLevel = "high" | "medium" | "low" | null;

interface CanonicalData {
  insured_name: string | null;
  insured_address: string | null;
  broker_name: string | null;
  mga_name: string | null;
  line_of_business: string | null;
  risk_description: string | null;
  region: string | null;
  country: string | null;
  annual_revenue: number | null;
  coverage_limit: number | null;
  deductible: number | null;
  premium: number | null;
  inception_date: string | null;
  expiry_date: string | null;
  prior_claims_count: number | null;
  prior_claims_amount: number | null;
  exclusions: string[] | null;
  confidence_scores: Record<string, ConfidenceLevel>;
  flags: Record<string, { severity: string; message: string }>;
  extracted_at: string;
  model: string;
}

interface Props {
  data: CanonicalData;
}

function ConfidenceBadge({ level }: { level: ConfidenceLevel }) {
  if (!level) return <span className="text-xs text-gray-300">—</span>;
  const styles: Record<string, string> = {
    high:   "bg-green-50 text-green-700 border border-green-100",
    medium: "bg-yellow-50 text-yellow-700 border border-yellow-100",
    low:    "bg-red-50 text-red-600 border border-red-100",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[level]}`}>
      {level}
    </span>
  );
}

function Field({
  label,
  value,
  confidence,
  flagged,
  format,
}: {
  label: string;
  value: string | number | null;
  confidence: ConfidenceLevel;
  flagged?: boolean;
  format?: "currency" | "date";
}) {
  const display = (() => {
    if (value === null || value === undefined || value === "") return null;
    if (format === "currency" && typeof value === "number") {
      return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 }).format(value);
    }
    if (format === "date" && typeof value === "string") {
      return new Date(value).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    }
    return String(value);
  })();

  return (
    <div className={`flex items-start justify-between py-2.5 border-b border-gray-50 last:border-0 ${flagged ? "bg-red-50 -mx-4 px-4 rounded" : ""}`}>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-400 uppercase tracking-wide font-medium">{label}</p>
        {display ? (
          <p className="text-sm text-gray-800 mt-0.5 font-medium">{display}</p>
        ) : (
          <p className="text-sm text-red-400 mt-0.5 italic">Missing</p>
        )}
      </div>
      <div className="ml-3 flex-shrink-0 mt-0.5">
        <ConfidenceBadge level={confidence} />
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">{title}</h3>
      <div className="bg-white rounded-xl border border-gray-100 px-4 divide-y divide-gray-50">
        {children}
      </div>
    </div>
  );
}

export default function CanonicalDataCard({ data }: Props) {
  const c = data.confidence_scores ?? {};
  const f = data.flags ?? {};

  return (
    <div className="mt-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Extracted Data</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {data.model} · {new Date(data.extracted_at).toLocaleTimeString()}
          </p>
        </div>
        {Object.keys(f).length > 0 && (
          <span className="text-xs bg-red-50 text-red-600 border border-red-100 px-3 py-1 rounded-full font-medium">
            {Object.keys(f).length} field{Object.keys(f).length > 1 ? "s" : ""} flagged
          </span>
        )}
      </div>

      {/* Party */}
      <Section title="Party">
        <Field label="Insured Name"    value={data.insured_name}    confidence={c.insured_name}    flagged={!!f.insured_name} />
        <Field label="Insured Address" value={data.insured_address} confidence={c.insured_address} flagged={!!f.insured_address} />
        <Field label="Broker"          value={data.broker_name}     confidence={c.broker_name}     flagged={!!f.broker_name} />
        <Field label="MGA"             value={data.mga_name}        confidence={c.mga_name} />
      </Section>

      {/* Risk */}
      <Section title="Risk">
        <Field label="Line of Business" value={data.line_of_business} confidence={c.line_of_business} flagged={!!f.line_of_business} />
        <Field label="Risk Description" value={data.risk_description} confidence={c.risk_description} />
        <Field label="Region"           value={data.region}           confidence={c.region} />
        <Field label="Country"          value={data.country}          confidence={c.country}          flagged={!!f.country} />
      </Section>

      {/* Financial */}
      <Section title="Financial">
        <Field label="Annual Revenue" value={data.annual_revenue} confidence={c.annual_revenue} flagged={!!f.annual_revenue} format="currency" />
        <Field label="Coverage Limit" value={data.coverage_limit} confidence={c.coverage_limit} flagged={!!f.coverage_limit} format="currency" />
        <Field label="Deductible"     value={data.deductible}     confidence={c.deductible}     format="currency" />
        <Field label="Premium"        value={data.premium}        confidence={c.premium}        flagged={!!f.premium} format="currency" />
      </Section>

      {/* Coverage Period */}
      <Section title="Coverage Period">
        <Field label="Inception Date" value={data.inception_date} confidence={c.inception_date} flagged={!!f.inception_date} format="date" />
        <Field label="Expiry Date"    value={data.expiry_date}    confidence={c.expiry_date}    flagged={!!f.expiry_date}    format="date" />
      </Section>

      {/* Claims */}
      <Section title="Prior Claims">
        <Field label="Claims Count"  value={data.prior_claims_count}  confidence={c.prior_claims_count} />
        <Field label="Claims Amount" value={data.prior_claims_amount} confidence={c.prior_claims_amount} format="currency" />
      </Section>

      {/* Exclusions */}
      {data.exclusions && data.exclusions.length > 0 && (
        <div className="mb-6">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Exclusions</h3>
          <div className="bg-white rounded-xl border border-gray-100 px-4 py-3 flex flex-wrap gap-2">
            {data.exclusions.map((ex, i) => (
              <span key={i} className="text-xs bg-gray-50 text-gray-600 border border-gray-100 px-3 py-1 rounded-full">
                {ex}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
