import { createFileRoute } from "@tanstack/react-router";
import { Workspace } from "@/components/askrepo/workspace";

export const Route = createFileRoute("/")({ component: Workspace });
