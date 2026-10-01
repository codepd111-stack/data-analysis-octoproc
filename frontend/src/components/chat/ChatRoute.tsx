"use client";

import { useSearchParams } from "next/navigation";
import ChatView from "./ChatView";

export default function ChatRoute() {
  const params = useSearchParams();
  // key forces a fresh ChatView whenever the URL params change (e.g. opening a past conversation)
  return (
    <ChatView
      key={params.toString()}
      initialDatasetId={params.get("dataset")}
      conversationId={params.get("conversation")}
    />
  );
}