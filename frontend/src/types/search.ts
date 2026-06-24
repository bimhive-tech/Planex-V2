// Global search result types — mirror the backend GlobalSearchView.

export interface SearchProject {
  id: string;
  name: string;
  location: string;
  is_archived: boolean;
}

export interface SearchActivity {
  id: string;
  name: string;
  code: string;
  project_id: string;
  project_name: string;
  path: string;
}

export interface SearchResponse {
  projects: SearchProject[];
  activities: SearchActivity[];
}
