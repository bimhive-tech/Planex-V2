"use client";

// Where a text box being edited on the canvas shows its formatting controls:
// a slot in the Properties panel on the right (register D4). The floating
// toolbar above the box used to cover the page and shrink the area left for
// the text itself. LayoutEditor provides the slot, ElementInspector renders
// it, and DescriptionPreview portals its RichTextEditor toolbar into it.
import { createContext, useContext } from "react";

export interface TextToolbarSlot {
  /** The panel element the toolbar renders into, or null when there is none
   * (the toolbar then stays with the text box). */
  slot: HTMLElement | null;
  setSlot: (el: HTMLElement | null) => void;
}

export const TextToolbarSlotContext = createContext<TextToolbarSlot>({ slot: null, setSlot: () => {} });

export function useTextToolbarSlot(): TextToolbarSlot {
  return useContext(TextToolbarSlotContext);
}
