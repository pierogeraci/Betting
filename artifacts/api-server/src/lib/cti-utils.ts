import { db, ctiActivityTable, type CtiSource } from "@workspace/db";
import type { Request } from "express";

export const trustFactorDefinitions = [
  { key: "multiple_accounts", label: "Collegamento di più account a un unico conto utente", weight: 1 },
  { key: "eu_bank_payment", label: "Pagamento mediante c/c bancario UE", weight: 1 },
  { key: "no_registration", label: "Assenza di registrazione", weight: 2 },
  { key: "no_identity_documents", label: "Assenza di iscrizione mediante documenti di riconoscimento", weight: 2 },
  { key: "third_party_provider", label: "Pagamento mediante provider terze parti", weight: 2 },
  { key: "crypto_payment_or_betting", label: "Pagamento e piazzamento mediante criptovalute", weight: 6 },
  { key: "offshore_bank_account", label: "Pagamento c/c offshore", weight: 6 },
] as const;

export const trustCalibrationNotice =
  "Modello prototipale: pesi e soglie sono provvisori e richiedono validazione/calibrazione prima di un uso operativo.";

export function riskBand(score: number, lowUpperExclusive: number, highLowerInclusive: number) {
  if (score < lowUpperExclusive) return "low" as const;
  if (score < highLowerInclusive) return "medium" as const;
  return "high" as const;
}

export function calculateTrust(
  vulnerabilityFactors: Array<{ key: string; present: boolean }>,
  threatMetrics: { averageBet: number; grossWinnings: number; winRate: number },
) {
  const factorDetails = trustFactorDefinitions.map((definition) => {
    const entered = vulnerabilityFactors.find((factor) => factor.key === definition.key);
    const present = entered?.present === true;
    return {
      key: definition.key,
      label: definition.label,
      weight: definition.weight,
      present,
      points: present ? definition.weight : 0,
    };
  });
  const vulnerabilityScore = factorDetails.reduce((sum, factor) => sum + factor.points, 0);
  const vulnerabilityBand = riskBand(vulnerabilityScore, 6, 12);

  const averageBetLevel =
    threatMetrics.averageBet < 50 ? 1 : threatMetrics.averageBet < 250 ? 2 : 3;
  const grossWinningsLevel =
    threatMetrics.grossWinnings < 1000
      ? 1
      : threatMetrics.grossWinnings < 5000
        ? 2
        : 3;
  const winRateLevel =
    threatMetrics.winRate < 0.25 ? 1 : threatMetrics.winRate < 0.5 ? 2 : 3;
  const threatScore = averageBetLevel + grossWinningsLevel + winRateLevel;
  const threatBand = riskBand(threatScore, 4, 7);
  const normalizedVulnerability = (vulnerabilityScore / 20) * 100;
  const normalizedThreat = ((threatScore - 3) / 6) * 100;
  const trustIndex = (normalizedVulnerability + normalizedThreat) / 2;
  const trustBand = riskBand(trustIndex, 33, 67);

  return {
    vulnerabilityScore,
    vulnerabilityBand,
    threatScore,
    threatBand,
    normalizedVulnerability: round2(normalizedVulnerability),
    normalizedThreat: round2(normalizedThreat),
    trustIndex: round2(trustIndex),
    trustBand,
    factorDetails,
    threatDetails: {
      averageBet: threatMetrics.averageBet,
      averageBetLevel,
      grossWinnings: threatMetrics.grossWinnings,
      grossWinningsLevel,
      winRate: threatMetrics.winRate,
      winRateLevel,
    },
    calibrationNotice: trustCalibrationNotice,
  };
}

export function calculateEventRisk(input: {
  oddsSources: number;
  marketVolume: number;
  unusualOdds: boolean;
}) {
  const points = {
    limitedOddsSources: input.oddsSources < 3 ? 1 : 0,
    unusualOdds: input.unusualOdds ? 2 : 0,
    elevatedMarketVolume: input.marketVolume >= 50000 ? 2 : input.marketVolume >= 10000 ? 1 : 0,
  };
  const score = Object.values(points).reduce((sum, value) => sum + value, 0);
  return {
    score,
    riskBand: score >= 4 ? "high" : score >= 2 ? "medium" : "low",
    details: points,
    note: "Rating euristico provvisorio basato sui dati di mercato forniti; da calibrare sui dati autorizzati.",
  };
}

export async function recordActivity(
  req: Request,
  action: string,
  entityType: string,
  entityId: string | number,
  entityLabel: string,
) {
  await db.insert(ctiActivityTable).values({
    action,
    entityType,
    entityId: String(entityId),
    entityLabel,
    actorId: "anonymous",
    actorLabel: "Operatore anonimo",
  });
}

export function serializeSource(source: CtiSource) {
  const today = new Date().toISOString().slice(0, 10);
  const legalStatus =
    source.legalStatus === "approved" && source.validUntil && source.validUntil < today
      ? "expired"
      : source.legalStatus;
  const effective = source.validFrom <= today && (!source.validUntil || source.validUntil >= today);
  return {
    ...source,
    legalStatus,
    reviewerId: "anonymous",
    reviewerLabel: "Operatore anonimo",
    createdAt: source.createdAt.toISOString(),
    updatedAt: source.updatedAt.toISOString(),
    ingestionAllowed: legalStatus === "approved" && effective,
  };
}

export function round2(value: number) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function toNumber(value: number | string | null | undefined) {
  if (value == null) return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}

export function toIso(value: Date | string | null | undefined) {
  if (value == null) return null;
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

export function toSqlDate(value: Date | string | null | undefined) {
  if (value == null) return value;
  return value instanceof Date ? value.toISOString().slice(0, 10) : value;
}

export function isSafeObjectPath(path: string | null | undefined) {
  return Boolean(path && path.startsWith("/objects/uploads/") && !path.includes(".."));
}
