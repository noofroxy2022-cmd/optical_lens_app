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
};

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
  delete: (id) => api.delete(`/prescriptions/${id}`),
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
  extract: (catalogId, saveToPreview = true) => api.post(`/pdf-import/extract/${catalogId}`, null, {
    params: { save_to_preview: saveToPreview }
  }),
  getExtractions: (catalogId, status) => api.get(`/pdf-import/extractions/${catalogId}`, { params: { status } }),
  updateExtraction: (id, data) => api.put(`/pdf-import/extractions/${id}`, data),
  confirm: (id) => api.post(`/pdf-import/extractions/${id}/confirm`),
  reject: (id, notes) => api.post(`/pdf-import/extractions/${id}/reject`, null, { params: { notes } }),
  bulkConfirm: (catalogId) => api.post(`/pdf-import/bulk-confirm/${catalogId}`),
};

export default api;
