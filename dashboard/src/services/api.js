import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

export const companyAPI = {
  getAll: (params) => api.get('/companies/', { params }),
  getById: (id) => api.get(`/companies/${id}`),
  create: (data) => api.post('/companies/', data),
  update: (id, data) => api.put(`/companies/${id}`, data),
  toggleActive: (id) => api.post(`/companies/${id}/toggle-active`),
  delete: (id, hard) => api.delete(`/companies/${id}`, { params: { hard_delete: hard } }),
  uploadLogo: (id, file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/companies/${id}/upload-logo`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
};

export const lensModelAPI = {
  getAll: (params) => api.get('/lens-models/', { params }),
  getById: (id) => api.get(`/lens-models/${id}`),
  create: (data) => api.post('/lens-models/', data),
  update: (id, data) => api.put(`/lens-models/${id}`, data),
  toggleActive: (id) => api.post(`/lens-models/${id}/toggle-active`),
  delete: (id) => api.delete(`/lens-models/${id}`),
  // Generic catalog-driven distinct-options facets for the targeted-search filter
  // panel (V1.0.1 UX hotfix). `params` is any subset of {company_id, lens_model_id,
  // index_value, category, design_variant, coating, color_variant, treatment_band,
  // availability, market_scope} - every field optional, no fixed order.
  getFilterOptions: (params) => api.get('/lens-models/filter-options', { params }),
};

// Back-compat alias: some pages import `lensAPI`; the real surface is lensModelAPI.
export const lensAPI = lensModelAPI;

export const lensVariantAPI = {
  getByModel: (modelId) => api.get(`/lens-models/${modelId}/variants`),
  create: (modelId, data) => api.post(`/lens-models/${modelId}/variants`, data),
};

export const powerRangeAPI = {
  getByModel: (modelId) => api.get(`/lens-models/${modelId}/power-ranges`),
  create: (modelId, data) => api.post(`/lens-models/${modelId}/power-ranges`, data),
};

export const prescriptionAPI = {
  getAll: () => api.get('/prescriptions/'),
  getById: (id) => api.get(`/prescriptions/${id}`),
  create: (data) => api.post('/prescriptions/', data),
  match: (id, { filters = null, preferStock = true, preferAspherical = true } = {}) =>
    api.post(`/prescriptions/${id}/match`, filters, {
      params: { prefer_stock: preferStock, prefer_aspherical: preferAspherical },
    }),
  // V1.0.1 availability-first product search. mode "automatic" | "targeted".
  // V1.2 core-workflow: use_mode (distance/reading/bifocal/progressive) and
  // technology_intent are passed straight through when present - the caller
  // (Prescriptions.js) already omits them entirely when not selected.
  search: (id, { mode = 'automatic', filters = null, preferStock = true, preferAspherical = true,
                 includeAlternatives = true, use_mode, technology_intent, customer_need } = {}) =>
    api.post(`/prescriptions/${id}/search`, {
      mode,
      filters,
      prefer_stock: preferStock,
      prefer_aspherical: preferAspherical,
      include_alternatives: includeAlternatives,
      ...(use_mode !== undefined ? { use_mode } : {}),
      ...(technology_intent !== undefined ? { technology_intent } : {}),
      ...(customer_need !== undefined ? { customer_need } : {}),
    }),
  delete: (id) => api.delete(`/prescriptions/${id}`),
};

export const backupAPI = {
  list: () => api.get('/backup/'),
  now: () => api.post('/backup/now'),
  restore: (name) => api.post('/backup/restore', { name }),
};

export const pdfImportAPI = {
  upload: (companyId, file) => {
    const formData = new FormData();
    formData.append('company_id', companyId);
    formData.append('file', file);
    return api.post('/pdf-import/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
  preview: (catalogId) => api.post(`/pdf-import/preview/${catalogId}`),
  // Sends the per-catalog import policy as schemas.ExtractRequest. dualPriceSemantics
  // is the generic reading rule (null = no special dual-price policy; the backend
  // 422s on any unsupported value - never a silent fallback).
  extract: (catalogId, { dualPriceSemantics = null, useVision = false, saveToPreview = true } = {}) =>
    api.post(`/pdf-import/extract/${catalogId}`, {
      dual_price_semantics: dualPriceSemantics,
      use_vision: useVision,
      save_to_preview: saveToPreview,
    }),
  getExtractions: (catalogId, status) => api.get(`/pdf-import/extractions/${catalogId}`, { params: { status } }),
  updateExtraction: (id, data) => api.put(`/pdf-import/extractions/${id}`, data),
  confirm: (id) => api.post(`/pdf-import/extractions/${id}/confirm`),
  reject: (id, notes) => api.post(`/pdf-import/extractions/${id}/reject`, null, { params: { notes } }),
  bulkConfirm: (catalogId) => api.post(`/pdf-import/bulk-confirm/${catalogId}`),
};

export default api;
