// App-wide 404. Lives at the app root so it renders for any unmatched route
// (outside the authenticated shell). Branded, with a way back.
import Link from "next/link";

import { Logo } from "@/components/ui/Logo";
import { ROUTES } from "@/lib/constants";
import styles from "./not-found.module.css";

export default function NotFound() {
  return (
    <div className={styles.wrap}>
      <Logo />
      <p className={styles.code}>404</p>
      <h1 className={styles.title}>Page not found</h1>
      <p className={styles.text}>The page you&apos;re looking for doesn&apos;t exist or was moved.</p>
      <Link href={ROUTES.dashboard} className={styles.link}>Back to dashboard</Link>
    </div>
  );
}
