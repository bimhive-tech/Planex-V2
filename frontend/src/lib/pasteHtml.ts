// Cleans HTML arriving on the clipboard (Word, Excel, Google Docs, a web page)
// down to the subset the report renderer understands.
//
// Whitelists the same tags, and the same style properties, as the backend
// sanitizer (apps/reports/richtext.py: _KEEP / _STYLE_PROPS). Keeping the two
// in step is the point: whatever survives here is what the editor shows, and
// whatever the editor shows is what the PDF draws. Anything else Word sends --
// its <style> blocks, <o:p> markers, mso-* declarations, class attributes
// pointing at CSS that isn't coming -- would be dropped server-side anyway,
// having first bloated the stored HTML and leaked Word's own styling into the
// editor on the way.

/** Tags kept as-is. Mirrors richtext.py's `_KEEP`. */
const KEEP = new Set([
  "b", "strong", "i", "em", "u", "span", "font",
  "p", "div", "li", "ul", "ol", "br",
  "table", "thead", "tbody", "tfoot", "tr", "td", "th",
]);

/** Tags dropped with their contents, not unwrapped. Mirrors `_DROP`. */
const DROP = new Set([
  "script", "style", "head", "title", "noscript", "iframe", "object", "embed",
  "meta", "link", "col", "colgroup",
]);

/** CSS properties read off `style=""`. Mirrors `_STYLE_PROPS`. */
const STYLE_PROPS = new Set([
  "color", "font-size", "font-weight", "font-style", "text-decoration", "text-align",
]);

function cleanStyle(el: Element): string {
  const raw = el.getAttribute("style");
  if (!raw) return "";
  const kept: string[] = [];
  for (const decl of raw.split(";")) {
    const at = decl.indexOf(":");
    if (at < 0) continue;
    const prop = decl.slice(0, at).trim().toLowerCase();
    const value = decl.slice(at + 1).trim();
    // `mso-*` and `-webkit-*` never reach the PDF, and a Word paste carries
    // dozens of them per element.
    if (!STYLE_PROPS.has(prop) || !value || value.startsWith("mso-")) continue;
    kept.push(`${prop}:${value}`);
  }
  return kept.join(";");
}

function scrub(node: Node, into: Node) {
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      into.appendChild(child.cloneNode(false));
      continue;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) continue; // comments, PIs

    const el = child as Element;
    // localName drops the namespace prefix, so Word's <o:p> is matched as "p"
    // -- test the full tag name, which keeps the prefix.
    const tag = el.tagName.toLowerCase();
    if (DROP.has(tag) || tag.includes(":")) continue;

    if (!KEEP.has(tag)) {
      scrub(el, into); // unwrap: drop the tag, keep what's inside it
      continue;
    }

    const copy = into.ownerDocument!.createElement(tag);
    const style = cleanStyle(el);
    if (style) copy.setAttribute("style", style);
    if (tag === "td" || tag === "th") {
      for (const key of ["colspan", "rowspan"]) {
        const span = el.getAttribute(key);
        if (span && /^\d+$/.test(span) && +span > 1) copy.setAttribute(key, span);
      }
    }
    if (tag === "font") {
      for (const key of ["color", "size"]) {
        const v = el.getAttribute(key);
        if (v) copy.setAttribute(key, v);
      }
    }
    scrub(el, copy);
    into.appendChild(copy);
  }
}

/** The clipboard's HTML, reduced to what the report can render. */
export function cleanPastedHtml(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const out = doc.createElement("div");
  scrub(doc.body, out);
  return out.innerHTML;
}
