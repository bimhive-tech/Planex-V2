// /settings → default to the Info subtab.
import { redirect } from "next/navigation";

export default function SettingsIndex() {
  redirect("/settings/info");
}
