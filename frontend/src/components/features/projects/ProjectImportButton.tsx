"use client";

// A button that opens the project Import dialog (register E1).
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import type { ProjectImportKind } from "@/lib/projectImport";
import { ProjectImportDialog } from "./ProjectImportDialog";

interface Props {
  projectId: string;
  kinds: ProjectImportKind[];
  label?: string;
  onImported: (kind: ProjectImportKind) => void;
}

export function ProjectImportButton({ projectId, kinds, label = "Import", onImported }: Props) {
  const [open, setOpen] = useState(false);
  if (kinds.length === 0) return null;
  return (
    <>
      <Button variant="secondary" size="sm" leadingIcon={<Icon name="upload" size={15} />}
        onClick={() => setOpen(true)}>
        {label}
      </Button>
      {open && (
        <ProjectImportDialog
          projectId={projectId} kinds={kinds} onClose={() => setOpen(false)} onImported={onImported}
        />
      )}
    </>
  );
}
