import { useSearchParams } from "react-router-dom";
import ChatView from "@/components/chat/ChatView";

export default function ChatPage() {
  const [params] = useSearchParams();
  // key forces a fresh ChatView whenever the URL params change (e.g. opening a past conversation)
  return (
    <ChatView
      key={params.toString()}
      initialDatasetId={params.get("dataset")}
      conversationId={params.get("conversation")}
    />
  );
}
