import { notFound } from "next/navigation";
import { SubmissionPage } from "@/components/SubmissionPage";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const numeric = Number(id);
  if (!Number.isInteger(numeric) || numeric < 1) notFound();
  return <SubmissionPage id={numeric} />;
}
