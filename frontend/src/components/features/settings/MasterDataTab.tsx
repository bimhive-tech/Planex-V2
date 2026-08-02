"use client";

// Settings -> Master Data: currencies, project types, and priorities — the
// lists that populate a project's own dropdowns. Internally segmented rather
// than three more top-level Settings tabs.
import { useState } from "react";

import { CompanySelector } from "./CompanySelector";
import { CurrencyList } from "./CurrencyList";
import { SimpleMasterList } from "./SimpleMasterList";
import styles from "./masterData.module.css";

type Section = "currencies" | "project-types" | "project-priorities";

const SECTIONS: { key: Section; label: string }[] = [
  { key: "currencies", label: "Currencies" },
  { key: "project-types", label: "Project Types" },
  { key: "project-priorities", label: "Priorities" },
];

interface Props {
  isPlatformAdmin: boolean;
  ownCompanyId: string;
}

export function MasterDataTab({ isPlatformAdmin, ownCompanyId }: Props) {
  const [companyId, setCompanyId] = useState(ownCompanyId);
  const [section, setSection] = useState<Section>("currencies");

  return (
    <div>
      <div className={styles.head}>
        {isPlatformAdmin && <CompanySelector value={companyId} onChange={setCompanyId} />}
        <nav className={styles.tabs} aria-label="Master data section">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              type="button"
              className={`${styles.tab} ${s.key === section ? styles.tabActive : ""}`}
              onClick={() => setSection(s.key)}
            >
              {s.label}
            </button>
          ))}
        </nav>
      </div>

      {section === "currencies" && <CurrencyList companyId={companyId} />}
      {section === "project-types" && (
        <SimpleMasterList
          resource="project-types" label="project type" labelPlural="project types" companyId={companyId}
        />
      )}
      {section === "project-priorities" && (
        <SimpleMasterList
          resource="project-priorities" label="priority" labelPlural="priorities" companyId={companyId}
        />
      )}
    </div>
  );
}
