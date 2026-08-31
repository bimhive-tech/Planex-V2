"use client";

// Right panel: exact position/size plus the selected element's own settings.
// Field lists are declarative per element type so adding a knob is one line.
import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/lib/api";
import {
  CHART_SOURCES, CHART_TYPES, FIELD_SOURCES, ITEM_CHART_SOURCES, ITEM_FIELD_SOURCES,
  ITEM_TABLE_SOURCES, TABLE_SOURCES,
} from "@/lib/reportElements";
import type { LayoutElement } from "@/lib/reportLayout";
import type { ReportData, ReportImage } from "@/types/report";
import styles from "./designer.module.css";

type PropField =
  | { path: string; label: string; kind: "text" }
  | { path: string; label: string; kind: "number"; step?: number }
  | { path: string; label: string; kind: "color" }
  // defaultOn: an unset prop reads as ON, not off — for a toggle whose
  // backend counterpart also defaults to shown when the prop is missing
  // (see pdf_canvas.py's _table_or_chart_title), so a freshly-placed
  // element's checkbox state matches what it actually renders.
  | { path: string; label: string; kind: "toggle"; defaultOn?: boolean }
  | { path: string; label: string; kind: "select"; options: { value: string; label: string }[] };

const ALIGN = [
  { value: "left", label: "Left" },
  { value: "center", label: "Center" },
  { value: "right", label: "Right" },
];

/** What a "toc" element lists — see apps/reports/pdf_canvas.py's
 * _draw_toc_element. "tables"/"figures"/"images" only pick up elements that
 * have their own "Show caption" toggle turned on elsewhere in the template. */
const TOC_VARIANTS = [
  { value: "contents", label: "Contents (pages)" },
  { value: "tables", label: "Tables" },
  { value: "figures", label: "Figures / charts" },
  { value: "images", label: "Images" },
];

/** Image source: a fixed logo/cover slot, a repeat-page photo slot (only
 * meaningful once the active page is marked "repeat" — see `repeating`), or
 * an image uploaded directly to this one box (report Customize tab only —
 * see the upload control below). */
const IMAGE_SOURCES = [
  { value: "left", label: "Left logo" },
  { value: "right", label: "Right logo" },
  { value: "cover", label: "Cover image" },
  { value: "repeat.item", label: "Repeat photo slot" },
  { value: "upload", label: "Uploaded image" },
];

/** Logo element source — left/right/cover are the fixed single slots;
 * "extra" picks one of any number of additional uploaded logos by index. */
const LOGO_SOURCES = [
  { value: "left", label: "Left logo" },
  { value: "right", label: "Right logo" },
  { value: "cover", label: "Cover image" },
  { value: "extra", label: "Additional logo (pick slot below)" },
  { value: "upload", label: "Uploaded image" },
];

/** Field lists per element type. `repeating` appends the item-scoped sources
 * (only resolvable on a page that clones itself per photo/zone/etc). */
function typeFields(type: string, repeating: boolean): PropField[] {
  switch (type) {
    case "text":
      return [
        { path: "text", label: "Text", kind: "text" },
        { path: "size", label: "Size (pt)", kind: "number" },
        { path: "color", label: "Color", kind: "color" },
        { path: "align", label: "Align", kind: "select", options: ALIGN },
        { path: "bold", label: "Bold", kind: "toggle" },
        { path: "italic", label: "Italic", kind: "toggle" },
      ];
    case "field":
      return [
        { path: "source", label: "Value", kind: "select",
          options: repeating ? [...FIELD_SOURCES, ...ITEM_FIELD_SOURCES] : FIELD_SOURCES },
        { path: "label", label: "Prefix label", kind: "text" },
        { path: "show_label", label: "Show prefix", kind: "toggle" },
        { path: "size", label: "Size (pt)", kind: "number" },
        { path: "color", label: "Color", kind: "color" },
        { path: "align", label: "Align", kind: "select", options: ALIGN },
        { path: "bold", label: "Bold", kind: "toggle" },
      ];
    case "image":
      return [
        { path: "source", label: "Image", kind: "select", options: IMAGE_SOURCES },
        { path: "slot", label: "Repeat slot (0, 1, 2…)", kind: "number" },
        { path: "show_caption", label: "Show caption", kind: "toggle" },
        { path: "fit", label: "Fit", kind: "select", options: [
          { value: "cover", label: "Cover (crop to fill)" }, { value: "contain", label: "Contain (show whole image)" }] },
        { path: "focal_x", label: "Crop focus — horizontal (0-100%)", kind: "number" },
        { path: "focal_y", label: "Crop focus — vertical (0-100%)", kind: "number" },
        { path: "border", label: "Border", kind: "toggle" },
        { path: "border_color", label: "Border color", kind: "color" },
        { path: "border_width", label: "Border width (mm)", kind: "number", step: 0.1 },
      ];
    case "logo":
      return [
        { path: "source", label: "Image", kind: "select", options: LOGO_SOURCES },
        { path: "slot", label: "Additional-logo slot (0, 1, 2…)", kind: "number" },
        { path: "border", label: "Border", kind: "toggle" },
        { path: "border_color", label: "Border color", kind: "color" },
        { path: "border_width", label: "Border width (mm)", kind: "number", step: 0.1 },
      ];
    case "rect":
      return [
        { path: "fill", label: "Fill", kind: "color" },
        { path: "stroke", label: "Border", kind: "color" },
        { path: "stroke_width", label: "Border width (mm)", kind: "number", step: 0.1 },
        { path: "radius", label: "Corner radius (mm)", kind: "number", step: 0.5 },
      ];
    case "ellipse":
      return [
        { path: "fill", label: "Fill", kind: "color" },
        { path: "stroke", label: "Border", kind: "color" },
        { path: "stroke_width", label: "Border width (mm)", kind: "number", step: 0.1 },
      ];
    case "line":
      return [
        { path: "stroke", label: "Color", kind: "color" },
        { path: "stroke_width", label: "Thickness (mm)", kind: "number", step: 0.1 },
      ];
    case "table":
      return [
        { path: "source", label: "Data", kind: "select",
          options: repeating ? [...TABLE_SOURCES, ...ITEM_TABLE_SOURCES] : TABLE_SOURCES },
        { path: "header_bg", label: "Header fill", kind: "color" },
        { path: "header_text", label: "Header text", kind: "color" },
        { path: "header_bold", label: "Bold header", kind: "toggle" },
        { path: "text_color", label: "Cell text color", kind: "color" },
        { path: "font_size", label: "Font size (pt)", kind: "number" },
        { path: "cell_padding", label: "Row height — cell padding (pt)", kind: "number", step: 0.5 },
        { path: "zebra", label: "Zebra rows", kind: "toggle" },
        { path: "zebra_color", label: "Zebra stripe color", kind: "color" },
        { path: "border", label: "Borders", kind: "toggle" },
        { path: "border_color", label: "Border color", kind: "color" },
        { path: "show_title", label: "Show title", kind: "toggle", defaultOn: true },
        { path: "title_text", label: "Title text (optional — defaults to the data source's name)", kind: "text" },
        { path: "show_caption", label: "Show caption", kind: "toggle" },
        { path: "caption", label: "Caption text (optional — defaults to the data source's name)", kind: "text" },
      ];
    case "chart":
      return [
        { path: "source", label: "Data", kind: "select",
          options: repeating ? [...CHART_SOURCES, ...ITEM_CHART_SOURCES] : CHART_SOURCES },
        { path: "chart_type", label: "Chart type", kind: "select", options: CHART_TYPES },
        { path: "legend", label: "Show legend", kind: "toggle" },
        { path: "color_a", label: "Series A", kind: "color" },
        { path: "color_b", label: "Series B", kind: "color" },
        { path: "show_title", label: "Show title", kind: "toggle", defaultOn: true },
        { path: "title_text", label: "Title text (optional — defaults to the data source's name)", kind: "text" },
        { path: "show_caption", label: "Show caption", kind: "toggle" },
        { path: "caption", label: "Caption text (optional — defaults to the data source's name)", kind: "text" },
      ];
    case "toc":
      return [
        { path: "variant", label: "Lists", kind: "select", options: TOC_VARIANTS },
        { path: "size", label: "Size (pt)", kind: "number" },
        { path: "row_height", label: "Row height (mm)", kind: "number", step: 0.5 },
        { path: "color", label: "Color", kind: "color" },
        { path: "exclude_cover", label: "Exclude cover page", kind: "toggle" },
      ];
    default:
      return [];
  }
}

interface Props {
  el: LayoutElement | null;
  onChange: (el: LayoutElement) => void;
  /** True when the active page (or master) is set to repeat — unlocks the
   * item-scoped source options above. */
  repeating?: boolean;
  /** Present only in the report-level "Customize" tab — enables the
   * "Uploaded image" source, since that image belongs to one specific
   * report, not a project-agnostic template. */
  reportId?: string;
  /** How many elements are currently selected — `el` is only ever set for
   * exactly one of them, so a multi-selection shows a group summary here
   * instead of per-type property fields (merging N different elements'
   * settings into one form isn't worth the complexity this editor needs). */
  selectedCount?: number;
  /** Deletes every currently-selected element at once. Only surfaced when
   * `selectedCount > 1` — a single selection already has Delete on the
   * canvas's own ⋯ menu and the Delete key. */
  onDeleteSelection?: () => void;
  /** Present only in the report-level "Customize" tab — the real zone list
   * for a table/chart element's scope-picker (bind this one element to a
   * specific zone instead of the whole project — see props.scope_zone_id,
   * read by apps/reports/pdf_canvas.py's resolve_table/resolve_chart). */
  liveData?: ReportData | null;
}

export function ElementInspector({
  el, onChange, repeating = false, reportId, selectedCount = 0, onDeleteSelection, liveData,
}: Props) {
  // Hooks must run every render regardless of `el`, so these sit above the
  // early returns below.
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (selectedCount > 1) {
    return (
      <aside className={styles.inspector} aria-label="Element properties">
        <h2 className={styles.panelTitle}>Properties</h2>
        <p className={styles.panelHint}>
          {selectedCount} elements selected. Drag any of them to move the group, or a corner handle to resize it.
        </p>
        {onDeleteSelection && (
          <Button variant="secondary" onClick={onDeleteSelection}>
            Delete {selectedCount} elements
          </Button>
        )}
      </aside>
    );
  }

  if (!el) {
    return (
      <aside className={styles.inspector} aria-label="Element properties">
        <h2 className={styles.panelTitle}>Properties</h2>
        <p className={styles.panelHint}>Select an element on the page to edit it.</p>
      </aside>
    );
  }

  const fields = typeFields(el.type, repeating);
  // Manual edits carried by a bound table — surfaced (and made reversible)
  // in the table block below.
  const hiddenRowCount = Array.isArray(el.props.hidden_rows) ? el.props.hidden_rows.length : 0;
  const hiddenColCount = Array.isArray(el.props.hidden_cols) ? el.props.hidden_cols.length : 0;
  const overrideCount = el.props.overrides && typeof el.props.overrides === "object"
    ? Object.keys(el.props.overrides as Record<string, unknown>).length
    : 0;

  async function handleUpload(file: File) {
    if (!reportId) return;
    setUploading(true);
    setUploadError(null);
    try {
      // Routed through a Next.js route handler (images-file), not the /api
      // rewrite proxy directly — see that route's docstring: the proxy can
      // drop a multipart body mid-stream during a dev Fast Refresh recompile.
      const created = await api.upload<ReportImage>(`/reports/${reportId}/images-file`, file, "image", { kind: "canvas" });
      onChange({
        ...el!,
        props: { ...el!.props, source: "upload", upload_id: created.id, upload_url: created.url },
      });
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Couldn't upload the image.");
    } finally {
      setUploading(false);
    }
  }

  function setProp(path: string, value: unknown) {
    onChange({ ...el!, props: { ...el!.props, [path]: value } });
  }

  function setGeom(key: "x" | "y" | "w" | "h", value: number) {
    onChange({ ...el!, [key]: value });
  }

  function setRotation(value: number) {
    // Keep it in [0, 360) so it always matches what the drag handle shows.
    const normalized = ((value % 360) + 360) % 360;
    onChange({ ...el!, rotation: normalized });
  }

  return (
    <aside className={styles.inspector} aria-label="Element properties">
      <h2 className={styles.panelTitle}>{el.type} properties</h2>

      <div className={styles.geomGrid}>
        {(["x", "y", "w", "h"] as const).map((k) => (
          <label key={k} className={styles.geomField}>
            <span>{k.toUpperCase()} (mm)</span>
            <input
              type="number"
              step={1}
              value={el[k]}
              onChange={(e) => setGeom(k, Number(e.target.value))}
            />
          </label>
        ))}
        <label className={styles.geomField}>
          <span>Rotation (°)</span>
          <input
            type="number"
            step={1}
            value={el.rotation ?? 0}
            onChange={(e) => setRotation(Number(e.target.value))}
          />
        </label>
      </div>

      {(el.type === "image" || el.type === "logo") && el.props.source === "upload" && (
        <div className={styles.uploadBlock}>
          {reportId ? (
            <>
              {el.props.upload_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- authed streaming URL, not an optimizable public asset
                <img className={styles.uploadPreview} src={String(el.props.upload_url)} alt="" />
              ) : (
                <p className={styles.panelHint}>No image uploaded yet.</p>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleUpload(file);
                  e.target.value = ""; // same file re-selectable next time
                }}
              />
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
              >
                {uploading ? "Uploading…" : el.props.upload_url ? "Change image" : "Upload image"}
              </Button>
              {uploadError && <p className="formError">{uploadError}</p>}
            </>
          ) : (
            <p className={styles.panelHint}>
              Uploading a specific image is only available on a report&apos;s Customize tab, not the
              project-agnostic template.
            </p>
          )}
        </div>
      )}

      {el.type === "description" && (
        <div className={styles.uploadBlock}>
          <p className={styles.panelHint}>
            <strong>Double-click this box on the canvas to open its formatting toolbar</strong> — bold,
            italic, underline, bullet/numbered lists, right/center/left alignment, text size, and text
            color all live there (this isn&apos;t a plain text box). The same toolbar also has table/chart/
            image embed buttons, and you can drag a table or chart from the palette straight into the text
            while editing. Continues onto extra pages if it doesn&apos;t fit this box.
          </p>
        </div>
      )}

      {el.type === "table" && el.props.source === "custom" && (
        <div className={styles.uploadBlock}>
          <p className={styles.panelHint}>
            Edit this table&apos;s cells directly on the canvas — click a cell to type, paste (Ctrl+V) cells
            copied from Excel, or use the row/column +/− controls right there on the page.
          </p>
        </div>
      )}

      {el.type === "table" && !!el.props.source && el.props.source !== "custom" && (
        <div className={styles.uploadBlock}>
          <p className={styles.panelHint}>
            Click a row&apos;s × on the canvas to hide it, or a column header&apos;s × to drop that
            column; double-click any cell to override its text. All three edit this table
            directly on the page.
          </p>
          {/* Hiding a row used to be one-way: nothing anywhere could bring it
              back, so a misclick was only recoverable by undo (and only before
              switching page). Both counts below are also the only signal that
              a table carries manual edits at all. */}
          {hiddenRowCount > 0 && (
            <div className={styles.propRow}>
              <span className={styles.panelHint}>
                {hiddenRowCount} row{hiddenRowCount === 1 ? "" : "s"} hidden
              </span>
              <Button
                type="button" variant="secondary" size="sm"
                onClick={() => setProp("hidden_rows", [])}
              >
                Show all rows
              </Button>
            </div>
          )}
          {hiddenColCount > 0 && (
            <div className={styles.propRow}>
              <span className={styles.panelHint}>
                {hiddenColCount} column{hiddenColCount === 1 ? "" : "s"} hidden
              </span>
              <Button
                type="button" variant="secondary" size="sm"
                onClick={() => setProp("hidden_cols", [])}
              >
                Show all columns
              </Button>
            </div>
          )}
          {overrideCount > 0 && (
            <div className={styles.propRow}>
              <span className={styles.panelHint}>
                {overrideCount} cell{overrideCount === 1 ? "" : "s"} manually edited
              </span>
              <Button
                type="button" variant="secondary" size="sm"
                onClick={() => setProp("overrides", {})}
              >
                Revert to source
              </Button>
            </div>
          )}
        </div>
      )}

      {(el.type === "table" || el.type === "chart") && liveData && el.props.source !== "custom" && (
        <div className={styles.uploadBlock}>
          <label className={styles.propField}>
            <span>Scope to one zone</span>
            <select
              value={String(el.props.scope_zone_id ?? "")}
              onChange={(e) => setProp("scope_zone_id", e.target.value || undefined)}
            >
              <option value="">Whole project (default)</option>
              {liveData.zones.filter((z) => z.id).map((z) => (
                <option key={z.id} value={z.id}>{z.name}</option>
              ))}
            </select>
          </label>
          <p className={styles.panelHint}>
            Binds this one element's data to a single zone instead of the whole project — e.g. so a "الموقف
            التنفيذي" table/chart pair can show just one zone&apos;s own numbers. Only affects zone-shaped
            sources (Progress by zone, Zone / area breakdown); other sources ignore it.
          </p>
        </div>
      )}

      <div className={styles.propFields}>
        {fields.map((f) => {
          const value = el.props[f.path];
          if (f.kind === "toggle") {
            return (
              <label key={f.path} className={styles.propToggle}>
                <input
                  type="checkbox"
                  checked={f.defaultOn ? value !== false : Boolean(value)}
                  onChange={(e) => setProp(f.path, e.target.checked)}
                />
                <span>{f.label}</span>
              </label>
            );
          }
          return (
            <label key={f.path} className={styles.propField}>
              <span>{f.label}</span>
              {f.kind === "select" ? (
                <select value={String(value ?? "")} onChange={(e) => setProp(f.path, e.target.value)}>
                  {f.options.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              ) : f.kind === "color" ? (
                <input
                  type="color"
                  value={String(value ?? "#000000")}
                  onChange={(e) => setProp(f.path, e.target.value)}
                />
              ) : f.kind === "number" ? (
                <input
                  type="number"
                  step={f.step ?? 1}
                  value={Number(value ?? 0)}
                  onChange={(e) => setProp(f.path, Number(e.target.value))}
                />
              ) : (
                <input
                  type="text"
                  value={String(value ?? "")}
                  onChange={(e) => setProp(f.path, e.target.value)}
                />
              )}
            </label>
          );
        })}
      </div>
    </aside>
  );
}
