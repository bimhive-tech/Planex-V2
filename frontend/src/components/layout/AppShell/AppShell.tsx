"use client";

// App shell: fixed sidebar (desktop/tablet) / off-canvas drawer (mobile) + header.
import { useState } from "react";

import { Sidebar } from "../Sidebar/Sidebar";
import { Header } from "../Header/Header";
import { Permission } from "@/lib/permissions";
import type { CurrentUser } from "@/types/auth";
import styles from "./AppShell.module.css";

interface Props {
  user: CurrentUser;
  children: React.ReactNode;
}

export function AppShell({ user, children }: Props) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const canSearch = user.is_platform_admin
    || user.permissions.includes(Permission.VIEW_PROJECTS)
    || user.permissions.includes(Permission.MANAGE_PROJECTS);

  return (
    <div className={styles.shell}>
      <Sidebar user={user} open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      {drawerOpen && <div className={styles.backdrop} onClick={() => setDrawerOpen(false)} />}
      <div className={styles.main}>
        <Header onMenuClick={() => setDrawerOpen(true)} canSearch={canSearch} />
        <main className={styles.content}>{children}</main>
      </div>
    </div>
  );
}
