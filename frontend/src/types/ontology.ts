export interface OntologyListItem {
  id: string
  name: string
  domain: string
  version: string
  status: string
  entity_count: number
  relation_count: number
  created_by: string
  created_at: string
  updated_at: string
}

export interface OntologyDetail extends OntologyListItem {
  description?: string
}
