import { apiClient } from './client'
import type { OntologyDetail, OntologyListItem } from '@/types/ontology'

export const ontologyApi = {
  list: (params?: { name?: string; page?: number; page_size?: number }) =>
    apiClient.get<{ items: OntologyListItem[]; total: number; page: number; page_size: number }>('/ontologies', { params }),
  get: (id: string) => apiClient.get<OntologyDetail>(`/ontologies/${id}`),
}
