/** @typedef {'direct-analysis' | 'docx-report' | null} AnalysisMode */
const DATASET_ID = /^[A-Za-z0-9_-]{1,128}$/;

/** @returns {AnalysisMode} */
export function readAnalysisMode(params) {
  const mode = params.get('analysis');
  return mode === 'direct-analysis' || mode === 'docx-report' ? mode : null;
}

/** @returns {string | null} */
export function readDatasetId(params) {
  const value = (params.get('dataset') || '').trim();
  return DATASET_ID.test(value) ? value : null;
}

/** @param {string} query @param {{ analysis?: AnalysisMode, dataset?: string | null }} selection */
export function dataAnalysisUrl(query, { analysis = null, dataset = null } = {}) {
  const params = new URLSearchParams(query);
  if (analysis) params.set('analysis', analysis);
  else params.delete('analysis');
  if (dataset) params.set('dataset', dataset);
  else params.delete('dataset');
  return `/projects/new?${params.toString()}`;
}

/** @param {string} query @param {AnalysisMode} mode */
export function analysisModeUrl(query, mode) {
  const params = new URLSearchParams(query);
  return dataAnalysisUrl(query, { analysis: mode, dataset: readDatasetId(params) });
}
