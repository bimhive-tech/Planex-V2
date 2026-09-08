"use client";

// Create / rename a scope node in the hierarchy. The choices mirror
// ProjectScope.ScopeType: the original five plus the Planex Code legend's own
// levels, so a hand-built tree can match what a coded P6 import produces.
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api, ApiError } from "@/lib/api";
import type { Scope } from "@/types/project";
import styles from "./projectForm.module.css";

const SCOPE_TYPES = [
  { value: "area", label: "Area" },
  { value: "sub_area", label: "Sub-area" },
  { value: "stage", label: "Stage" },
  { value: "zone", label: "Zone" },
  { value: "part", label: "Part" },
  { value: "unit", label: "Unit" },
  { value: "level", label: "Level" },
  { value: "building", label: "Building" },
  { value: "discipline", label: "Discipline" },
  { value: "sub_discipline", label: "Sub-discipline" },
  { value: "phase", label: "Phase" },
];

const DISCIPLINES = [
  { value: "", label: "Unclassified" },
  { value: "concrete", label: "Concrete" },
  { value: "architecture", label: "Architecture" },
  { value: "electrical", label: "Electrical" },
  { value: "mechanical", label: "Mechanical" },
  { value: "other", label: "Other" },
];

interface Props {
  open: boolean;
  projectId: string;
  parentId: string | null; // where to attach (create)
  scope: Scope | null; // edit when set
  defaultType?: string;
  onClose: () => void;
  onSaved: () => void;
}

export function ScopeFormModal({ open, projectId, parentId, scope, defaultType = "phase", onClose, onSaved }: Props) {
  const isEdit = !!scope;
  const [name, setName] = useState("");
  const [type, setType] = useState(defaultType);
  const [plannedStart, setPlannedStart] = useState("");
  const [plannedFinish, setPlannedFinish] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(scope?.name ?? "");
      setType(scope?.scope_type ?? defaultType);
      setPlannedStart(scope?.planned_start ?? "");
      setPlannedFinish(scope?.planned_finish ?? "");
      setDiscipline(scope?.discipline ?? "");
      setError(null);
    }
  }, [open, scope, defaultType]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const payload = {
      name, scope_type: type,
      planned_start: plannedStart || null, planned_finish: plannedFinish || null,
      discipline: type === "phase" ? discipline : "",
    };
    try {
      if (isEdit && scope) {
        await api.patch(`/projects/${projectId}/scopes/${scope.id}/`, payload);
      } else {
        await api.post(`/projects/${projectId}/scopes/`, { ...payload, parent: parentId });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save.");
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={isEdit ? "Edit scope" : "Add scope"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="scope-form" disabled={submitting}>
            {submitting ? "Saving…" : isEdit ? "Save" : "Add"}
          </Button>
        </>
      }
    >
      <form id="scope-form" onSubmit={handleSubmit} className={styles.form}>
        <Select label="Level" options={SCOPE_TYPES} value={type} onChange={(e) => setType(e.target.value)} />
        <Input label="Name" name="name" required autoFocus placeholder="e.g. Substructure / Zone A"
          value={name} onChange={(e) => setName(e.target.value)} />
        {type === "phase" && (
          <Select label="Discipline" options={DISCIPLINES} value={discipline}
            onChange={(e) => setDiscipline(e.target.value)} />
        )}
        <div className={styles.row2}>
          <Input label="Planned start" type="date" name="planned_start"
            value={plannedStart} onChange={(e) => setPlannedStart(e.target.value)} />
          <Input label="Planned finish" type="date" name="planned_finish"
            value={plannedFinish} onChange={(e) => setPlannedFinish(e.target.value)} />
        </div>
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
