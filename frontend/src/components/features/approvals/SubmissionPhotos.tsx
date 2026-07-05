"use client";

// Compact evidence-photo strip for a submission card — lets a reviewer actually
// see what the submitter attached. Read-only; opens the full image in a new tab.
// `img.url` is already a full "/api/..." path (same convention as progress photos).
import Image from "next/image";

import type { ProjectSubmission } from "@/types/project";
import styles from "./submissionPhotos.module.css";

export function SubmissionPhotos({ images }: { images: ProjectSubmission["images"] }) {
  if (!images || images.length === 0) return null;
  return (
    <div className={styles.strip}>
      {images.map((img) => (
        <a key={img.id} href={img.url} target="_blank" rel="noopener noreferrer"
          className={styles.thumbLink} title={img.caption || "View photo"}>
          <Image className={styles.thumb} src={img.url} alt={img.caption || "Submission photo"}
            width={64} height={64} unoptimized />
        </a>
      ))}
    </div>
  );
}
