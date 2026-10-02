import { notFound } from "next/navigation";
import { SubmissionPage } from "@/components/SubmissionPage";
import { STEPS } from "@/lib/guide";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ step?: string }>;
};

export default async function Page({ params, searchParams }: Props) {
  const { id } = await params;
  const { step } = await searchParams;
  const numeric = Number(id);
  if (!Number.isInteger(numeric) || numeric < 1) notFound();
  const parsedStep = Number(step);
  const guidedStep =
    Number.isInteger(parsedStep) && parsedStep >= 1 && parsedStep <= STEPS.length
      ? parsedStep
      : null;
  return <SubmissionPage id={numeric} step={guidedStep} />;
}
