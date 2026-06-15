"use client";

// Create / rename a scope node (phase, zone, building, area) in the hierarchy.
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api, ApiError } from "@/lib/api";
import type { Scope } from "@/types/project";
import styles from "./projectForm.module.css";

const SCOPE_TYPES = [
  { value: "phase", label: "Phase" },
  { value: "zone", label: "Zone" },
  { value: "building", label: "Building" },
  { value: "area", label: "Area" },
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
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(scope?.name ?? "");
      setType(scope?.scope_type ?? defaultType);
      setError(null);
    }
  }, [open, scope, defaultType]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (isEdit && scope) {
        await api.patch(`/projects/${projectId}/scopes/${scope.id}/`, { name, scope_type: type });
      } else {
        await api.post(`/projects/${projectId}/scopes/`, { name, scope_type: type, parent: parentId });
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
      title={isEdit ? "Rename scope" : "Add scope"}
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
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
