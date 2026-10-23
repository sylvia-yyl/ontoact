/** Workshop-style app definition (mirrors backend workshop_apps.AppDefinition) and the widget catalogue. */

export type Event = { set_variable?: string | null; field?: string | null; navigate?: string | null }
export type Widget = { id: string; type: WidgetType; title: string; source?: string | null; path: string; props: Record<string, unknown>; on_select?: Event | null; region?: string | null }
export type LayoutItem = { i: string; x: number; y: number; w: number; h: number }
/** layout coordinates are relative to the widget's region (see templates.ts); a page without a template is one 24-column grid. */
export type Page = { id: string; title: string; widgets: Widget[]; layout: LayoutItem[]; template?: string }
export type SourceFilter = { field: string; op: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in'; value: unknown }
/** time_field: the row field the app-wide time range filters on. */
export type StudyRunSource = { id: string; kind: 'study_run'; label: string; study_id: string; node: string; time_field?: string | null }
/** Every object of one type (optionally filtered), read from a snapshot shared by the app's sources. */
export type ObjectSetSource = { id: string; kind: 'object_set'; label: string; object_type: string; select?: string[]; filters?: SourceFilter[]; limit?: number; time_field?: string | null }
export type AlertsSource = { id: string; kind: 'alerts'; label: string; status?: 'open' | 'acknowledged' | 'resolved' | null; subject_type?: string | null; limit?: number; time_field?: string | null }
/** Objects grouped on the server (count / sum / avg / min / max); a join picks up a dimension object's properties by key, bands turn numbers into categories. */
export type AggregateSource = { id: string; kind: 'aggregate'; label: string; object_type: string; group_by: string[]; metrics: Array<{ key: string; op: 'count' | 'sum' | 'avg' | 'min' | 'max' | 'exact_distinct'; property?: string | null }>
  filters?: SourceFilter[]; time_field?: string | null; join?: { object_type: string; on: string; key?: string | null; select: string[] } | null
  bands?: Array<{ field: string; into: string; cuts: Array<[number, string]>; otherwise: string }> }
/** A shared ontology query. version: a range such as "^1" (empty = the current major, fixed on save); params: a value or { variable }. */
export type QuerySource = { id: string; kind: 'query'; label: string; query: string; version?: string; params?: Record<string, unknown>; time_field?: null }
export type ColumnRole = 'dimension' | 'name' | 'category' | 'metric' | 'measure' | 'time' | 'latitude' | 'longitude' | 'identifier'
export type OutputColumn = { name: string; type: string; role: ColumnRole; label: string }
/** What a query returns: single = one row of metrics, 2d / 3d = grouped by one / two fields, table = rows. */
export type OutputSchema = { shape: 'single' | '2d' | '3d' | 'table'; path: string; columns: OutputColumn[] }
export type QueryParam = { name: string; field: string; label?: string; required?: boolean; default?: unknown }
export type QuerySummary = { api_name: string; name: string; description: string; latest_version: string; kind: string; object_type: string | null
  params: QueryParam[]; output_schema: OutputSchema; references?: number; updated_at: string }
export type DataSource = StudyRunSource | ObjectSetSource | AlertsSource | AggregateSource | QuerySource
export type Variable = { id: string; label: string; default?: unknown }
export type TimeRange = 'all' | '1d' | '7d' | '30d'
export type AppSettings = { time_range: TimeRange; refresh_minutes: 0 | 1 | 5 | 15 }
export const DEFAULT_SETTINGS: AppSettings = { time_range: 'all', refresh_minutes: 0 }
/** Ranges end at the latest timestamp in the data, not today, so historical datasets still have a "last 7 days". */
export const TIME_RANGES: Array<[TimeRange, string]> = [['all', 'All time'], ['1d', 'Last 24 hours'], ['7d', 'Last 7 days'], ['30d', 'Last 30 days']]
export const REFRESH_OPTIONS: Array<[AppSettings['refresh_minutes'], string]> = [[0, 'Manual'], [1, 'Every minute'], [5, 'Every 5 minutes'], [15, 'Every 15 minutes']]
export type AppDefinition = { schema: 'workshop-app/v1'; data_sources: DataSource[]; variables: Variable[]; pages: Page[]; settings?: AppSettings }
export type AppRecord = { id: string; name: string; description: string; head_version: number; head: { version: number; definition: AppDefinition } }
export type ResolvedStudyRun = { source_id: string; kind: 'study_run'; study_id: string; node: string; run_id: string; status: string; scenario_id: string; scenario_revision: number; completed_at: string | null; outputs: Record<string, unknown> | null; artifacts: Array<{ id: string; artifact_type: string; content_digest: string }> }
/** time: the window the server applied (anchor = latest time in the source, rows after `after` are kept). */
export type TimeWindow = { range: string; field?: string | null; anchor?: string | null; after?: string | null }
export type ResolvedOntologySource = { source_id: string; kind: 'object_set' | 'alerts' | 'aggregate'; status: string; completed_at: string | null; data_view_id?: string
  query?: string; version?: string; output_schema?: OutputSchema
  outputs: Record<string, unknown> & { count: number; truncated?: boolean; time?: TimeWindow } }
export type ResolvedSource = ResolvedStudyRun | ResolvedOntologySource

export type FieldKind = 'text' | 'number' | 'boolean' | 'select' | 'scalar_path' | 'field' | 'variable' | 'page' | 'list' | 'color'
export type FieldSpec = { key: string; label: string; kind: FieldKind; options?: string[]; item?: FieldSpec[]; help?: string }
export type WidgetType = 'kpi_strip' | 'table' | 'bar_chart' | 'coverage_grid' | 'facet_list' | 'select' | 'stat_row' | 'banner' | 'action_list' | 'action_detail' | 'rerun_button'
  | 'donut_chart' | 'rank_bars' | 'alert_list' | 'geo_map'
export type WidgetSpec = { type: WidgetType; label: string; description: string; w: number; h: number; usesArray: boolean; selectable: boolean; props: FieldSpec[]; defaults: Record<string, unknown> }

const FORMAT = ['text', 'number', 'money', 'percent', 'date']
const WHERE: FieldSpec[] = [{ key: 'where_field', label: 'Condition field', kind: 'field' }, { key: 'where_equals', label: 'Equals', kind: 'text' }]
const FILTER: FieldSpec[] = [{ key: 'filter_field', label: 'Field filtered by variable', kind: 'field', help: 'Show a row when this field equals (or its array contains) the variable value' }, { key: 'filter_variable', label: 'Filter variable', kind: 'variable' }]

export const WIDGETS: WidgetSpec[] = [
  { type: 'kpi_strip', label: 'KPI strip', description: 'A row of large numbers. The first one can be colored by the sign of another value.', w: 24, h: 3, usesArray: false, selectable: false,
    props: [{ key: 'items', label: 'Metrics', kind: 'list', item: [{ key: 'label', label: 'Name', kind: 'text' }, { key: 'path', label: 'Value', kind: 'scalar_path' }, { key: 'format', label: 'Format', kind: 'select', options: FORMAT },
      { key: 'note', label: 'Note (supports {path|format})', kind: 'text' }, { key: 'tone_path', label: 'Color by the sign of', kind: 'scalar_path' }] }],
    defaults: { items: [] } },
  { type: 'table', label: 'Table', description: 'Shows a list as a table; clicking a row can set a variable and open a page.', w: 16, h: 10, usesArray: true, selectable: true,
    props: [{ key: 'columns', label: 'Columns', kind: 'list', item: [{ key: 'label', label: 'Header', kind: 'text' }, { key: 'field', label: 'Field', kind: 'field' }, { key: 'format', label: 'Format', kind: 'select', options: FORMAT },
      { key: 'badge', label: 'Show as badge', kind: 'boolean' }, { key: 'tone_rule', label: 'Highlight rule', kind: 'select', options: ['', 'gt', 'lt', 'truthy'] }, { key: 'tone_value', label: 'Threshold', kind: 'number' }, { key: 'tone_field', label: 'Field to test (default: this column)', kind: 'field' }] },
      ...FILTER, { key: 'sort_field', label: 'Sort by', kind: 'field' }, { key: 'sort_desc', label: 'Descending', kind: 'boolean' }, { key: 'max_rows', label: 'Max rows', kind: 'number' }],
    defaults: { columns: [] } },
  { type: 'bar_chart', label: 'Stacked bar chart', description: 'Groups by a field; each series sums the rows that match its condition.', w: 16, h: 8, usesArray: true, selectable: false,
    props: [{ key: 'x_field', label: 'Group by (x axis)', kind: 'field' }, { key: 'series', label: 'Series', kind: 'list', item: [{ key: 'label', label: 'Name', kind: 'text' }, { key: 'value_field', label: 'Sum field (empty = count)', kind: 'field' }, ...WHERE, { key: 'color', label: 'Color', kind: 'color' }] }, ...FILTER],
    defaults: { series: [] } },
  { type: 'coverage_grid', label: 'Time grid', description: 'One row of values over time per item; negatives are highlighted.', w: 24, h: 12, usesArray: true, selectable: false,
    props: [{ key: 'label_field', label: 'Row label field', kind: 'field' }, { key: 'values_field', label: 'Values (array field)', kind: 'field' }, { key: 'columns_path', label: 'Column headers (array path)', kind: 'scalar_path' },
      { key: 'emphasis_field', label: 'Bold when field is true', kind: 'field' }, { key: 'weeks', label: 'Columns shown by default', kind: 'number' }, ...FILTER],
    defaults: { weeks: 12 } },
  { type: 'facet_list', label: 'Facet filter', description: 'Lists the values of a field with counts; clicking sets a variable.', w: 6, h: 5, usesArray: true, selectable: false,
    props: [{ key: 'field', label: 'Field', kind: 'field' }, { key: 'options_path', label: 'All values (optional array path)', kind: 'scalar_path' }, { key: 'variable', label: 'Set variable', kind: 'variable' }],
    defaults: {} },
  { type: 'select', label: 'Dropdown', description: 'Pick one item from a list into a variable.', w: 6, h: 3, usesArray: true, selectable: false,
    props: [{ key: 'value_field', label: 'Value field', kind: 'field' }, { key: 'label_field', label: 'Label field', kind: 'field' }, { key: 'variable', label: 'Set variable', kind: 'variable' }, { key: 'allow_all', label: 'Allow “All”', kind: 'boolean' }],
    defaults: { allow_all: true } },
  { type: 'stat_row', label: 'Stats', description: 'Counts, sums or ratios over a list.', w: 6, h: 3, usesArray: true, selectable: false,
    props: [{ key: 'items', label: 'Items', kind: 'list', item: [{ key: 'label', label: 'Name', kind: 'text' }, { key: 'agg', label: 'Aggregation', kind: 'select', options: ['count', 'sum', 'ratio'] }, { key: 'field', label: 'Sum field', kind: 'field' }, ...WHERE,
      { key: 'format', label: 'Format', kind: 'select', options: FORMAT }] }, ...FILTER],
    defaults: { items: [] } },
  { type: 'banner', label: 'Banner', description: 'Shows a message when any rows match; {count} is the number of rows.', w: 16, h: 2, usesArray: true, selectable: false,
    props: [{ key: 'template', label: 'Text', kind: 'text' }, ...WHERE, ...FILTER],
    defaults: { template: '{count} items need attention' } },
  { type: 'action_list', label: 'Action list', description: 'Candidate actions; selecting one sets a variable.', w: 8, h: 14, usesArray: true, selectable: false,
    props: [{ key: 'label_field', label: 'Name field', kind: 'field' }, { key: 'subtitle', label: 'Subtitle (supports {field|format})', kind: 'text' }, { key: 'variable', label: 'Set variable on select', kind: 'variable' },
      { key: 'only_applicable', label: 'Only applicable actions', kind: 'boolean' }, { key: 'max_rows', label: 'Max items', kind: 'number' }, { key: 'navigate', label: 'Open page on click', kind: 'page' }],
    defaults: { label_field: 'label' } },
  { type: 'action_detail', label: 'Action detail and approval', description: 'The selected candidate: before/after metrics, actions, explanation, decision package review and apply.', w: 16, h: 18, usesArray: true, selectable: false,
    props: [{ key: 'variable', label: 'Variable', kind: 'variable' }, { key: 'metrics', label: 'Before/after metrics', kind: 'list', item: [{ key: 'label', label: 'Name', kind: 'text' }, { key: 'before_path', label: 'Before (source path)', kind: 'scalar_path' },
      { key: 'after_field', label: 'After (action field)', kind: 'field' }, { key: 'format', label: 'Format', kind: 'select', options: FORMAT }] }, { key: 'explain', label: 'Offer explanation', kind: 'boolean' }],
    defaults: { metrics: [], explain: true } },
  { type: 'rerun_button', label: 'Re-run button', description: 'Re-runs the source study on the latest ontology data and shows each step and the before/after change.', w: 8, h: 2, usesArray: false, selectable: false,
    props: [{ key: 'label', label: 'Button text', kind: 'text' }, { key: 'steps', label: 'Values to compare', kind: 'list', item: [{ key: 'label', label: 'Name', kind: 'text' }, { key: 'path', label: 'Value', kind: 'scalar_path' }, { key: 'format', label: 'Format', kind: 'select', options: FORMAT }] }],
    defaults: { label: 'Re-run and update', steps: [] } },
  { type: 'donut_chart', label: 'Donut chart', description: 'Shares by group with the total in the middle; clicking a slice sets a variable. Severity levels use red, amber and green.', w: 8, h: 7, usesArray: true, selectable: false,
    props: [{ key: 'category_field', label: 'Group by', kind: 'field' }, { key: 'value_field', label: 'Sum field (empty = count)', kind: 'field' }, { key: 'center_label', label: 'Center label', kind: 'text' },
      { key: 'variable', label: 'Set variable on click', kind: 'variable' }, ...FILTER],
    defaults: { center_label: 'Total' } },
  { type: 'rank_bars', label: 'Rank bars', description: 'Top N groups by sum or count; clicking a row sets a variable.', w: 8, h: 7, usesArray: true, selectable: false,
    props: [{ key: 'label_field', label: 'Group by', kind: 'field' }, { key: 'value_field', label: 'Sum field (empty = count)', kind: 'field' }, { key: 'max_rows', label: 'Show top', kind: 'number' },
      { key: 'format', label: 'Number format', kind: 'select', options: FORMAT }, { key: 'color', label: 'Color (empty = palette)', kind: 'color' }, { key: 'variable', label: 'Set variable on click', kind: 'variable' }, ...FILTER],
    defaults: { max_rows: 10, format: 'number' } },
  { type: 'alert_list', label: 'Alert list', description: 'Alerts or risks ordered by severity; bind the alerts path of a rule-alert data source.', w: 10, h: 8, usesArray: true, selectable: false,
    props: [{ key: 'title', label: 'Title (supports {field|format})', kind: 'text' }, { key: 'subtitle', label: 'Subtitle (supports {field|format})', kind: 'text' },
      { key: 'severity_field', label: 'Severity field', kind: 'field' }, { key: 'time_field', label: 'Time field', kind: 'field' }, { key: 'key_field', label: 'Field to set on click', kind: 'field' },
      { key: 'variable', label: 'Set variable on click', kind: 'variable' }, { key: 'navigate', label: 'Open page on click', kind: 'page' }, { key: 'max_rows', label: 'Max items', kind: 'number' }, ...FILTER],
    defaults: { title: '{rule_name}: {subject_id}', severity_field: 'severity', time_field: 'window_end', key_field: 'subject_id', max_rows: 50 } },
  { type: 'geo_map', label: 'Map', description: 'Rows with coordinates as points, sized by a value and colored by group; can draw links.', w: 14, h: 12, usesArray: true, selectable: false,
    props: [{ key: 'lat_field', label: 'Latitude field', kind: 'field' }, { key: 'lng_field', label: 'Longitude field', kind: 'field' }, { key: 'label_field', label: 'Name field', kind: 'field' },
      { key: 'size_field', label: 'Size field (empty = same size)', kind: 'field' }, { key: 'color_field', label: 'Color group field', kind: 'field' }, { key: 'key_field', label: 'Field to set on click', kind: 'field' },
      { key: 'variable', label: 'Set variable on click', kind: 'variable' }, { key: 'to_lat_field', label: 'Link end latitude', kind: 'field' }, { key: 'to_lng_field', label: 'Link end longitude', kind: 'field' }, ...FILTER],
    defaults: { key_field: 'id' } },
]

export const specOf = (type: string) => WIDGETS.find(row => row.type === type)


export function nextId(prefix: string, taken: string[]) {
  let index = 1
  while (taken.includes(`${prefix}${index}`)) index += 1
  return `${prefix}${index}`
}
