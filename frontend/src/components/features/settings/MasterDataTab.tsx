"use client";

// Settings -> Master Data: currencies, project types, priorities and the party
// roster — the lists that populate a project's own dropdowns. Internally
// segmented rather than four more top-level Settings tabs.
import { useState } from "react";

import { CompanySelector } from "./CompanySelector";
import { CurrencyList } from "./CurrencyList";
import { PartyMasterList } from "./PartyMasterList";
import { SimpleMasterList } from "./SimpleMasterList";
import styles from "./masterData.module.css";

type Section =
  | "currencies" | "project-types" | "project-priorities" | "parties";

const SECTIONS: { key: Section; label: string }[] = [
  { key: "currencies", label: "Currencies" },
  { key: "project-types", label: "Project Types" },
  { key: "project-priorities", label: "Priorities" },
  // One roster, not a tab per role: a project picks who its owner, consultant,
  // contractor and sub-contractor are from the same list of companies.
  { key: "parties", label: "Parties" },
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
      {section === "parties" && <PartyMasterList companyId={companyId} />}
    </div>
  );
}
