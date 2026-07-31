"use client";

import { useParams } from "next/navigation";

import { BlueprintWorkbench } from "@/components/blueprint/blueprint-workbench";

export default function BlueprintPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  return <BlueprintWorkbench projectId={projectId} />;
}
