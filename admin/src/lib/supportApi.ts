import { apiRequest } from './apiClient';

export async function getSupportHealth() {
  return apiRequest('/health');
}
