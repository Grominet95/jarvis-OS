const JRV_CODE_RE = /JRV-[A-Z]{3}-\d{3}/gi;

export function extractJrvCodes(query) {
  const matches = String(query).match(JRV_CODE_RE);
  if (!matches) return [];
  return [...new Set(matches.map((c) => c.toUpperCase()))];
}

export function lookupErrorCodes(db, codes) {
  if (!codes.length) return [];
  const stmt = db.prepare(
    `SELECT code, domain, severity, title_fr, message_fr, resolution_fr, docs, modules
     FROM error_codes WHERE code = ?`
  );
  return codes.map((code) => stmt.get(code)).filter(Boolean);
}

export function formatErrorCodeBlock(row) {
  const docs = row.docs ? row.docs.split("|").filter(Boolean) : [];
  const modules = row.modules ? row.modules.split("|").filter(Boolean) : [];
  const lines = [
    `Code: ${row.code}`,
    `Severity: ${row.severity}`,
    `Title: ${row.title_fr}`,
    `Message: ${row.message_fr}`,
    `Resolution: ${row.resolution_fr}`,
  ];
  if (docs.length) lines.push(`Docs: ${docs.join(", ")}`);
  if (modules.length) lines.push(`Modules: ${modules.join(", ")}`);
  return lines.join("\n");
}

export function errorCodesToContextRows(rows) {
  return rows.map((row) => ({
    doc_path: "09-operations/error-codes.md",
    doc_title: "Error codes reference",
    section_title: row.code,
    body: formatErrorCodeBlock(row),
    priority: 99,
    rank: -20,
    rerank: -20,
  }));
}
