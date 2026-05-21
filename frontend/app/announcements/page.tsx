import { format } from "date-fns";
import { api } from "../../lib/api";
import AnnouncementsClient from "../../components/AnnouncementsClient";

async function getData() {
  const today = format(new Date(), "yyyy-MM-dd");
  const announcements = await api.announcements({ date: today, limit: "500" }).catch(() => []);
  const sorted = [...announcements].sort(
    (a, b) => (b.importance_score ?? 0) - (a.importance_score ?? 0)
  );
  return { sorted, today };
}

export default async function AnnouncementsPage() {
  const { sorted, today } = await getData();
  return <AnnouncementsClient allAnnouncements={sorted} today={today} />;
}
